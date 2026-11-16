"""Account commands for Monarch CLI."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import typer
from graphql import parse
from monarchmoney.monarchmoney import BalanceHistoryRow  # type: ignore[import-untyped]

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, NetworkError, ValidationError
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.accounts import list_accounts, refresh_accounts
from ._mutation import extract_id, mutation_result
from .transactions import _create_or_get_transaction

app = typer.Typer(
    help="Account management",
    no_args_is_help=True,
)

_CREATE_INVESTMENTS_ACCOUNT_MUTATION = parse(
    """
    mutation Common_CreateManualInvestmentsAccount(
      $input: CreateManualInvestmentsAccountInput!
    ) {
      createManualInvestmentsAccount(input: $input) {
        account { id }
        errors { message code }
      }
    }
    """
)


def _resolve_format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    """Resolve explicit output flags."""
    return OutputFormat.JSON if json_output else format


def _parse_initial_holdings(values: list[str] | None) -> list[dict[str, Any]]:
    """Parse repeatable security_id=quantity options for account creation."""
    holdings: list[dict[str, Any]] = []
    seen_security_ids: set[str] = set()
    for value in values or []:
        security_id, separator, raw_quantity = value.partition("=")
        security_id = security_id.strip()
        raw_quantity = raw_quantity.strip()
        if not separator or not security_id or not raw_quantity:
            raise ValidationError(
                "--holding values must use security_id=quantity.",
                field="holding",
                details={"value": value},
            )
        if security_id in seen_security_ids:
            raise ValidationError(
                f"Duplicate --holding security ID: {security_id}.",
                field="holding",
            )
        try:
            quantity = Decimal(raw_quantity)
        except InvalidOperation as exc:
            raise ValidationError(
                f"Invalid holding quantity: {raw_quantity}.",
                field="holding",
            ) from exc
        if not quantity.is_finite():
            raise ValidationError(
                f"Holding quantity must be finite: {raw_quantity}.",
                field="holding",
            )
        seen_security_ids.add(security_id)
        holdings.append({"securityId": security_id, "quantity": float(quantity)})
    return holdings


def _investment_account_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the create-manual-investments-account payload."""
    payload = data.get("createManualInvestmentsAccount")
    if not isinstance(payload, dict):
        raise APIError(
            "Monarch response did not include createManualInvestmentsAccount.",
            details={"response": data},
        )
    errors = payload.get("errors")
    if errors:
        first = errors[0] if isinstance(errors, list) else errors
        message = first.get("message") if isinstance(first, dict) else str(first)
        raise APIError(
            str(message or "Monarch rejected investment account creation."),
            details={"errors": errors},
        )
    return payload


def _fetch_all_account_transactions(client: Any, account_id: str) -> list[dict[str, Any]]:
    """Fetch all raw transactions for one account with paging."""
    limit = 500
    offset = 0
    results: list[dict[str, Any]] = []
    while True:
        raw_page: Any = run_api_call(
            partial(
                client.get_transactions,
                limit=limit,
                offset=offset,
                start_date=None,
                end_date=None,
                search="",
                category_ids=[],
                account_ids=[account_id],
                tag_ids=[],
                transaction_visibility="all_transactions",
            )
        )
        page_results = (raw_page.get("allTransactions") or {}).get("results") or []
        results.extend(page_results)
        if len(page_results) < limit:
            break
        offset += limit
    return results


def _transaction_match_text(raw_txn: dict[str, Any]) -> str:
    """Build text used for exclusion matching."""
    merchant = raw_txn.get("merchant") or {}
    return " ".join(
        filter(
            None,
            [
                raw_txn.get("plaidName"),
                raw_txn.get("displayName"),
                raw_txn.get("name"),
                merchant.get("name"),
            ],
        )
    )


def _should_exclude_transaction(
    raw_txn: dict[str, Any],
    *,
    exclude_category_names: set[str],
    exclude_pattern: re.Pattern[str],
) -> bool:
    """Return whether a source transaction should be skipped in the clone."""
    category = raw_txn.get("category") or {}
    if category.get("name") in exclude_category_names:
        return True
    return bool(exclude_pattern.search(_transaction_match_text(raw_txn)))


def _source_description(raw_txn: dict[str, Any]) -> str:
    """Choose a stable description for cloned manual transactions."""
    merchant = raw_txn.get("merchant") or {}
    return (
        merchant.get("name")
        or raw_txn.get("merchantName")
        or raw_txn.get("plaidName")
        or raw_txn.get("displayName")
        or raw_txn.get("name")
        or "Imported transaction"
    )


def _source_account_type_names(source_account: dict[str, Any]) -> tuple[str | None, str | None]:
    """Normalize source account type/subtype names for manual account creation."""
    type_info = source_account.get("type") or {}
    subtype_info = source_account.get("subtype") or {}

    account_type = type_info.get("name")
    account_type_display = str(type_info.get("display") or "").strip().lower().replace(" ", "_")
    if not account_type and account_type_display:
        account_type = account_type_display

    account_subtype = subtype_info.get("name")
    subtype_display = str(subtype_info.get("display") or "").strip().lower().replace(" ", "_")
    if not account_subtype and subtype_display:
        account_subtype = subtype_display

    return account_type, account_subtype


def _should_clone_via_history(source_account: dict[str, Any]) -> bool:
    """Use balance-history mirroring for investment/brokerage accounts."""
    type_info = source_account.get("type") or {}
    subtype_info = source_account.get("subtype") or {}
    type_name = str(type_info.get("name") or "").lower()
    type_display = str(type_info.get("display") or "").lower()
    subtype_name = str(subtype_info.get("name") or "").lower()

    return (
        type_name == "brokerage"
        or subtype_name == "brokerage"
        or "investment" in type_display
        or bool(source_account.get("holdingsCount"))
    )


def _fetch_account_history_rows(client: Any, account_id: str) -> list[dict[str, Any]]:
    """Fetch raw balance history snapshots for one account."""
    raw_history: Any = run_api_call(lambda: client.get_account_history(int(account_id)))
    if not isinstance(raw_history, list):
        raise RuntimeError(f"Unexpected account history shape for account {account_id}.")
    return [row for row in raw_history if isinstance(row, dict) and row.get("date") is not None]


def _balance_history_rows(
    source_account: dict[str, Any],
    history_rows: list[dict[str, Any]],
) -> list[BalanceHistoryRow]:
    """Convert raw account history rows to uploadable Monarch balance history rows."""
    account_name = source_account.get("displayName")
    rows: list[BalanceHistoryRow] = []
    for row in history_rows:
        amount = row.get("signedBalance")
        date_text = row.get("date")
        if amount is None or not date_text:
            continue
        rows.append(
            BalanceHistoryRow(
                date=datetime.fromisoformat(f"{date_text}T00:00:00"),
                amount=float(amount),
                account_name=account_name,
            )
        )
    return rows


_CURRENCY_PAIR_PATTERN = re.compile(r"^[A-Z]{3}\.[A-Z]{3}$", re.IGNORECASE)
_SOURCE_CURRENCY_PATTERN = re.compile(r"^\s*([A-Z]{3})\b", re.IGNORECASE)
_INTEREST_PATTERN = re.compile(r"\b(?:CREDIT|DEBIT)\s+INT\b|\bINTEREST\b|\bSYEP\b", re.IGNORECASE)
_USD_NOTE_AMOUNT_PATTERN = re.compile(
    r"(?:=|->|corrected\s+to)\s*([+-]?[\d,]+(?:\.\d+)?)\s+USD\b",
    re.IGNORECASE,
)
_SOURCE_CLONE_ID_PATTERN = re.compile(
    r"\bSource IBKR transaction ([A-Za-z0-9_-]+)\.",
    re.IGNORECASE,
)
_REFRESH_WAIT_TIMEOUT_BUFFER_SECONDS = 30


def _find_account(accounts: list[dict[str, Any]], account_id: str) -> dict[str, Any] | None:
    """Find one account by exact ID in an already-fetched account list."""
    return next((account for account in accounts if str(account.get("id")) == account_id), None)


def _refresh_account_scope(account: list[str] | None, active_linked: bool) -> list[str] | None:
    """Resolve refresh scope without treating an empty selection as all accounts."""
    if not active_linked:
        return list(account) if account else None
    if account:
        raise typer.BadParameter("Use either --account or --active-linked, not both")
    ids = [
        str(row["id"])
        for row in list_accounts()
        if row.get("id") and row.get("is_active") and row.get("is_manual") is False
    ]
    if not ids:
        raise typer.BadParameter("No active linked accounts available to refresh")
    return ids


def _wait_refresh_result(
    *,
    client: Any,
    account_ids: list[str] | None,
    timeout: int,
    delay: int,
) -> dict[str, Any]:
    """Wait for refresh completion without turning a late poll into a hard CLI failure."""
    try:
        complete: bool = run_api_call(
            lambda: client.request_accounts_refresh_and_wait(
                account_ids=account_ids,
                timeout=timeout,
                delay=delay,
            ),
            timeout_seconds=timeout + delay + _REFRESH_WAIT_TIMEOUT_BUFFER_SECONDS,
            max_retries=0,
        )
    except NetworkError as exc:
        status_timeout = timeout + delay + _REFRESH_WAIT_TIMEOUT_BUFFER_SECONDS
        timed_out_wait = (
            exc.details.get("timeout_seconds") == status_timeout
            and exc.details.get("attempts") == 1
        )
        if not timed_out_wait:
            raise
        complete = run_api_call(
            lambda: client.is_accounts_refresh_complete(account_ids=account_ids),
            timeout_seconds=max(delay, 5),
            max_retries=0,
        )
        result = {
            "status": "complete" if complete else "timeout",
            "complete": complete,
            "account_ids": account_ids,
            "wait_error": exc.to_dict(),
        }
        return result

    return {
        "status": "complete" if complete else "timeout",
        "complete": complete,
        "account_ids": account_ids,
    }


def _resolve_clone_target(
    accounts: list[dict[str, Any]],
    *,
    source_account_id: str,
    target_account_id: str | None,
    target_name: str,
) -> dict[str, Any] | None:
    """Resolve one reusable manual destination or fail on ambiguity."""
    if target_account_id:
        target = _find_account(accounts, target_account_id)
        if target is None:
            raise typer.BadParameter(f"Target account {target_account_id} not found.")
        if target_account_id == source_account_id:
            raise typer.BadParameter("Source and target account IDs must differ.")
        if not target.get("isManual"):
            raise typer.BadParameter(f"Target account {target_account_id} is not manual.")
        return target

    exact_matches = [
        account
        for account in accounts
        if str(account.get("id")) != source_account_id and account.get("displayName") == target_name
    ]
    if len(exact_matches) > 1:
        duplicate_ids = ", ".join(str(account.get("id")) for account in exact_matches)
        raise typer.BadParameter(
            f"Multiple accounts named {target_name!r}: {duplicate_ids}. "
            "Pass --target-account to choose one before retrying."
        )
    if not exact_matches:
        return None
    target = exact_matches[0]
    if not target.get("isManual"):
        raise typer.BadParameter(
            f"Existing account {target.get('id')} named {target_name!r} is not manual."
        )
    return target


def _load_normalization_overrides(path: Path | None) -> dict[str, dict[str, Any]]:
    """Load explicit source-row USD normalization overrides from CSV."""
    if path is None:
        return {}
    if not path.is_file():
        raise typer.BadParameter(f"Normalization CSV not found: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        required = {"source_transaction_id", "amount"}
        missing = sorted(required - fieldnames)
        if missing:
            raise typer.BadParameter(
                f"Normalization CSV missing required columns: {', '.join(missing)}"
            )

        overrides: dict[str, dict[str, Any]] = {}
        for row_number, row in enumerate(reader, start=2):
            source_id = str(row.get("source_transaction_id") or "").strip()
            if not source_id:
                raise typer.BadParameter(
                    f"Normalization CSV row {row_number} has no source_transaction_id."
                )
            if source_id in overrides:
                raise typer.BadParameter(
                    f"Normalization CSV repeats source transaction {source_id}."
                )
            try:
                amount = Decimal(str(row.get("amount") or "").replace(",", ""))
            except InvalidOperation as exc:
                raise typer.BadParameter(
                    f"Normalization CSV row {row_number} has invalid amount {row.get('amount')!r}."
                ) from exc
            overrides[source_id] = {
                "amount": amount,
                "category_id": str(row.get("category_id") or "").strip() or None,
                "notes": str(row.get("notes") or "").strip() or None,
            }
    return overrides


def _usd_amount_from_note(note: str) -> Decimal | None:
    """Extract the final signed USD amount encoded in an FX or Sign note."""
    matches = _USD_NOTE_AMOUNT_PATTERN.findall(note)
    if not matches:
        return None
    try:
        return Decimal(matches[-1].replace(",", ""))
    except InvalidOperation:
        return None


def _is_currency_pair_transaction(raw_txn: dict[str, Any]) -> bool:
    """Return whether a row name is a direct currency pair such as USD.KRW."""
    names = [raw_txn.get("plaidName"), (raw_txn.get("merchant") or {}).get("name")]
    return any(_CURRENCY_PAIR_PATTERN.fullmatch(str(name).strip()) for name in names if name)


def _is_interest_transaction(raw_txn: dict[str, Any]) -> bool:
    """Return whether category or row text identifies interest-like activity."""
    category_name = str((raw_txn.get("category") or {}).get("name") or "")
    return category_name == "Interest" or bool(
        _INTEREST_PATTERN.search(_transaction_match_text(raw_txn))
    )


def _source_currency(raw_txn: dict[str, Any]) -> str | None:
    """Infer a leading ISO currency code from the provider row name."""
    match = _SOURCE_CURRENCY_PATTERN.match(str(raw_txn.get("plaidName") or ""))
    return match.group(1).upper() if match else None


def _clone_notes(raw_txn: dict[str, Any], normalized_note: str | None = None) -> str:
    """Preserve evidence and add a durable source transaction ID."""
    source_id = str(raw_txn.get("id") or "unknown")
    note = (normalized_note if normalized_note is not None else raw_txn.get("notes") or "").strip()
    source_suffix = f"Source IBKR transaction {source_id}."
    if source_suffix in note:
        return note
    if not note:
        return source_suffix
    separator = " " if note.endswith((".", ";")) else ". "
    return f"{note}{separator}{source_suffix}"


def _source_clone_id(raw_txn: dict[str, Any]) -> str | None:
    """Read the durable source transaction ID from a cloned row note."""
    match = _SOURCE_CLONE_ID_PATTERN.search(str(raw_txn.get("notes") or ""))
    return match.group(1) if match else None


def _index_target_clones(target_transactions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index cloned rows by source ID and reject an already-corrupt duplicate set."""
    indexed: dict[str, dict[str, Any]] = {}
    for txn in target_transactions:
        source_id = _source_clone_id(txn)
        if source_id is None:
            continue
        if source_id in indexed:
            raise RuntimeError(
                f"Target account contains multiple rows for source transaction {source_id}."
            )
        indexed[source_id] = txn
    return indexed


def _target_clone_drift_fields(
    prepared: dict[str, Any],
    target_txn: dict[str, Any],
) -> list[str]:
    """Return mutable fields that differ from the current normalized source row."""
    fields: list[str] = []
    source_txn = prepared["source"]
    if str(target_txn.get("date") or "") != str(source_txn.get("date") or ""):
        fields.append("date")
    if Decimal(str(target_txn.get("amount") or 0)) != prepared["amount"]:
        fields.append("amount")
    target_category_id = str((target_txn.get("category") or {}).get("id") or "")
    if target_category_id != str(prepared["category_id"] or ""):
        fields.append("category")
    if str(target_txn.get("notes") or "") != prepared["notes"]:
        fields.append("notes")
    return fields


def _history_signature(history_rows: list[dict[str, Any]]) -> list[tuple[str, Decimal]]:
    """Build a stable date/balance signature for source and target history comparison."""
    signature: list[tuple[str, Decimal]] = []
    for row in history_rows:
        date_value = row.get("date")
        amount = row.get("signedBalance")
        if date_value is None or amount is None:
            continue
        signature.append((str(date_value), Decimal(str(amount))))
    return sorted(signature)


def _normalized_brokerage_row(
    raw_txn: dict[str, Any],
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the target amount/category/note for one brokerage source row."""
    source_id = str(raw_txn.get("id") or "")
    source_amount = Decimal(str(raw_txn.get("amount") or 0))
    source_category = raw_txn.get("category") or {}
    source_note = str(raw_txn.get("notes") or "")
    override = overrides.get(source_id)

    if override:
        amount = override["amount"]
        category_id = override.get("category_id") or source_category.get("id")
        note = _clone_notes(raw_txn, override.get("notes"))
        normalization_source = "override"
    else:
        note_amount = _usd_amount_from_note(source_note)
        amount = note_amount if note_amount is not None else source_amount
        category_id = source_category.get("id")
        note = _clone_notes(raw_txn)
        normalization_source = "note" if note_amount is not None else "source"

        match_text = _transaction_match_text(raw_txn).upper()
        if note_amount is None and _source_currency(raw_txn) == "USD":
            if "CREDIT INT" in match_text:
                amount = abs(source_amount)
                note = _clone_notes(
                    raw_txn,
                    f"Sign: normalized USD credit interest to +{amount:.2f} USD for clean clone",
                )
                normalization_source = "sign_rule"
            elif "DEBIT INT" in match_text:
                amount = -abs(source_amount)
                note = _clone_notes(
                    raw_txn,
                    f"Sign: normalized USD debit interest to {amount:.2f} USD for clean clone",
                )
                normalization_source = "sign_rule"

    return {
        "source": raw_txn,
        "source_id": source_id,
        "source_amount": source_amount,
        "amount": amount,
        "category_id": str(category_id) if category_id else None,
        "notes": note,
        "normalization_source": normalization_source,
    }


def _prepare_brokerage_ledger(
    source_transactions: list[dict[str, Any]],
    *,
    overrides: dict[str, dict[str, Any]],
    exclude_category_names: set[str],
    exclude_pattern: re.Pattern[str],
    min_interest_amount: Decimal,
    min_other_amount: Decimal,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select key brokerage activity and normalize target USD values."""
    source_ids = {str(txn.get("id") or "") for txn in source_transactions}
    unknown_overrides = sorted(set(overrides) - source_ids)
    if unknown_overrides:
        raise typer.BadParameter(
            "Normalization CSV references unknown source transaction IDs: "
            + ", ".join(unknown_overrides)
        )

    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    interest_category_id = next(
        (
            str((txn.get("category") or {}).get("id"))
            for txn in source_transactions
            if (txn.get("category") or {}).get("name") == "Interest"
            and (txn.get("category") or {}).get("id")
        ),
        None,
    )
    for txn in sorted(
        source_transactions,
        key=lambda item: (item.get("date") or "", str(item.get("id") or "")),
    ):
        prepared = _normalized_brokerage_row(txn, overrides)
        category_name = str((txn.get("category") or {}).get("name") or "")
        match_text = _transaction_match_text(txn)
        absolute_amount = abs(prepared["amount"])

        if category_name in exclude_category_names or _is_currency_pair_transaction(txn):
            prepared["reason"] = "currency_conversion"
            excluded.append(prepared)
        elif category_name == "Financial Fees" or "CUSTODY FEE" in match_text.upper():
            prepared["reason"] = "minor_fee"
            excluded.append(prepared)
        elif exclude_pattern.search(match_text):
            prepared["reason"] = "excluded_pattern"
            excluded.append(prepared)
        elif _is_interest_transaction(txn):
            if prepared["normalization_source"] == "source" and _source_currency(txn) not in {
                None,
                "USD",
            }:
                prepared["reason"] = "missing_usd_evidence"
                excluded.append(prepared)
            elif absolute_amount < min_interest_amount:
                prepared["reason"] = "minor_interest"
                excluded.append(prepared)
            else:
                if interest_category_id and prepared["normalization_source"] != "override":
                    prepared["category_id"] = interest_category_id
                prepared["reason"] = "material_interest"
                kept.append(prepared)
        elif category_name in {"Buy", "Sell"}:
            if prepared["normalization_source"] == "source":
                prepared["reason"] = "missing_usd_evidence"
                excluded.append(prepared)
            else:
                prepared["reason"] = "trade"
                kept.append(prepared)
        elif absolute_amount < min_other_amount:
            prepared["reason"] = "minor_activity"
            excluded.append(prepared)
        else:
            prepared["reason"] = "material_activity"
            kept.append(prepared)
    return kept, excluded


def _ledger_summary_row(prepared: dict[str, Any]) -> dict[str, Any]:
    """Build an auditable dry-run row without leaking internal Decimal values."""
    source = prepared["source"]
    return {
        "source_transaction_id": prepared["source_id"],
        "date": source.get("date"),
        "description": _source_description(source),
        "source_amount": float(prepared["source_amount"]),
        "amount": float(prepared["amount"]),
        "category": (source.get("category") or {}).get("name"),
        "category_id": prepared["category_id"],
        "reason": prepared["reason"],
        "normalization_source": prepared["normalization_source"],
        "notes": prepared["notes"],
    }


@app.command("list")
@handle_errors
def list_cmd(
    format: Annotated[
        OutputFormat | None,
        typer.Option(
            "-f",
            "--format",
            help="Output format (plain, json, table, csv, compact)",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (shortcut for --format json)",
        ),
    ] = False,
    ndjson: Annotated[
        bool,
        typer.Option(
            "--ndjson",
            help="Output as newline-delimited JSON (one object per line)",
        ),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Output raw API response without transformation",
        ),
    ] = False,
) -> None:
    """List all linked accounts.

    Shows accounts from all linked financial institutions with
    current balances and metadata.

    Examples:
        monarch accounts list                # Plain format (default in terminal)
        monarch accounts list --json         # JSON format
        monarch accounts list --format table # Table format
        monarch accounts list | jq .         # Auto-JSON when piped
        monarch accounts list --raw          # Raw API response
    """
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON
    if ndjson:
        output_format = OutputFormat.COMPACT  # Will handle NDJSON below

    with spinner("Fetching accounts..."):
        if raw:
            # Raw mode: return untransformed API response
            client = get_authenticated_client()
            data: Any = run_api_call(lambda: client.get_accounts())
        else:
            # Normal mode: use service with transformation
            data = list_accounts()

    # Handle NDJSON output
    if ndjson:
        import json

        if isinstance(data, list):
            for item in data:
                print(json.dumps(item, default=str))
        else:
            # For raw mode with dict, output as single line
            print(json.dumps(data, default=str))
        return

    output(data, output_format, raw=False)


@app.command()
@handle_errors
def refresh(
    account: Annotated[
        list[str] | None,
        typer.Option(
            "-a",
            "--account",
            help="Specific account ID(s) to refresh (repeatable). Refreshes all if not provided.",
        ),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait",
            help="Wait until account refresh completes.",
        ),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            help="Maximum seconds to wait when --wait is used.",
        ),
    ] = 300,
    delay: Annotated[
        int,
        typer.Option(
            "--delay",
            help="Polling delay in seconds when --wait is used.",
        ),
    ] = 10,
    active_linked: Annotated[
        bool,
        typer.Option("--active-linked", help="Only active, non-manual linked accounts."),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Request account refresh from linked institutions.

    Triggers a sync with your linked banks and financial institutions.
    By default, refreshes all accounts. Use --account to refresh specific ones.

    Note: This initiates a background refresh. Account data may take a few
    minutes to update fully.

    Examples:
        monarch accounts refresh                        # Refresh all accounts
        monarch accounts refresh -a ACC123              # Refresh one account
        monarch accounts refresh -a ACC123 -a ACC456    # Refresh multiple
    """
    # Convert None to None (not empty list) for the service
    account_ids = _refresh_account_scope(account, active_linked)

    with spinner("Requesting account refresh..."):
        if wait:
            client = get_authenticated_client()
            result = _wait_refresh_result(
                client=client,
                account_ids=account_ids,
                timeout=timeout,
                delay=delay,
            )
        else:
            result = refresh_accounts(account_ids)

    refresh_extra: dict[str, Any] = {key: value for key, value in result.items() if key != "status"}
    output(
        mutation_result(
            status=str(result.get("status", "requested")),
            entity="account",
            ids=account_ids,
            result=result,
            **refresh_extra,
        ),
        _resolve_format(format, json_output),
    )


@app.command("refresh-status")
@handle_errors
def refresh_status(
    account: Annotated[
        list[str] | None,
        typer.Option(
            "-a",
            "--account",
            help="Specific account ID(s) to check (repeatable). Checks all if not provided.",
        ),
    ] = None,
    active_linked: Annotated[
        bool,
        typer.Option("--active-linked", help="Only active, non-manual linked accounts."),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Check whether account refresh is complete."""
    account_ids = _refresh_account_scope(account, active_linked)
    with spinner("Checking account refresh status..."):
        client = get_authenticated_client()
        complete: bool = run_api_call(
            lambda: client.is_accounts_refresh_complete(account_ids=account_ids)
        )
    output({"complete": complete, "account_ids": account_ids}, _resolve_format(format, json_output))


@app.command("history")
@handle_errors
def history(
    account_id: Annotated[str, typer.Argument(help="Account ID")],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Inspect account balance history over time."""
    with spinner("Fetching account history..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_account_history(int(account_id)))
    output(data, _resolve_format(format, json_output))


@app.command("holdings")
@handle_errors
def holdings(
    account_id: Annotated[str, typer.Argument(help="Account ID")],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get investment holdings for one account."""
    with spinner("Fetching account holdings..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_account_holdings(int(account_id)))
    output(data, _resolve_format(format, json_output))


@app.command("recent-balances")
@handle_errors
def recent_balances(
    start: Annotated[
        str | None,
        typer.Option("--start", help="Start date filter (YYYY-MM-DD)"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Pull recent account balance snapshots."""
    with spinner("Fetching recent balances..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_recent_account_balances(start_date=start))
    output(data, _resolve_format(format, json_output))


@app.command("snapshots")
@handle_errors
def snapshots(
    start: Annotated[str, typer.Option("--start", help="Start date (YYYY-MM-DD)")],
    timeframe: Annotated[
        str,
        typer.Option("--timeframe", help="Snapshot timeframe accepted by Monarch API"),
    ] = "month",
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get account snapshots by type."""
    with spinner("Fetching account snapshots..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.get_account_snapshots_by_type(start_date=start, timeframe=timeframe)
        )
    output(data, _resolve_format(format, json_output))


@app.command("aggregate-snapshots")
@handle_errors
def aggregate_snapshots(
    start: Annotated[str | None, typer.Option("--start", help="Start date (YYYY-MM-DD)")] = None,
    end: Annotated[str | None, typer.Option("--end", help="End date (YYYY-MM-DD)")] = None,
    account_type: Annotated[
        str | None,
        typer.Option("--account-type", help="Account type filter"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get net worth snapshots over time."""
    start_date = datetime.fromisoformat(start).date() if start else None
    end_date = datetime.fromisoformat(end).date() if end else None
    with spinner("Fetching aggregate snapshots..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.get_aggregate_snapshots(
                start_date=start_date,
                end_date=end_date,
                account_type=account_type,
            )
        )
    output(data, _resolve_format(format, json_output))


@app.command("create")
@handle_errors
def create(
    name: Annotated[str, typer.Option("--name", help="Account name")],
    account_type: Annotated[str, typer.Option("--type", help="Account type")],
    subtype: Annotated[str, typer.Option("--subtype", help="Account subtype")],
    balance: Annotated[float, typer.Option("--balance", help="Starting balance")] = 0,
    in_net_worth: Annotated[
        bool,
        typer.Option(
            "--include-in-net-worth/--exclude-from-net-worth",
            help="Include the manual account in net worth.",
        ),
    ] = True,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a manual account."""
    with spinner("Creating manual account..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.create_manual_account(
                account_type=account_type,
                account_sub_type=subtype,
                is_in_net_worth=in_net_worth,
                account_name=name,
                account_balance=balance,
            )
        )
    output(
        mutation_result(
            status="created",
            entity="account",
            id=extract_id(data, ("createManualAccount", "account")),
            result=data,
        ),
        _resolve_format(format, json_output),
    )


@app.command("create-investments")
@handle_errors
def create_investments(
    name: Annotated[str, typer.Option("--name", help="Manual investment account name")],
    subtype: Annotated[str, typer.Option("--subtype", help="Investment account subtype")],
    holding: Annotated[
        list[str] | None,
        typer.Option(
            "--holding",
            help="Initial Monarch security and quantity as security_id=quantity. Repeatable.",
        ),
    ] = None,
    in_net_worth: Annotated[
        bool,
        typer.Option(
            "--include-in-net-worth/--exclude-from-net-worth",
            help="Include the manual investment account in net worth.",
        ),
    ] = True,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a holdings-tracked manual investment account.

    Refuses an existing exact-name account to prevent duplicate retries. Monarch
    derives market values from its own security catalog; custom prices are not
    supported by the account or holding mutation.
    """
    initial_holdings = _parse_initial_holdings(holding)

    with spinner("Creating manual investment account..."):
        client = get_authenticated_client()
        before: Any = run_api_call(lambda: client.get_accounts())
        duplicate_ids = [
            str(account.get("id"))
            for account in before.get("accounts", [])
            if account.get("displayName") == name
        ]
        if duplicate_ids:
            raise ValidationError(
                f"An account named {name!r} already exists; refusing a duplicate.",
                field="name",
                details={"account_ids": duplicate_ids},
            )

        data: Any = run_api_call(
            lambda: client.gql_call(
                "Common_CreateManualInvestmentsAccount",
                _CREATE_INVESTMENTS_ACCOUNT_MUTATION,
                {
                    "input": {
                        "name": name,
                        "subtype": subtype,
                        "manualInvestmentsTrackingMethod": "holdings",
                        "initialHoldings": initial_holdings,
                    }
                },
            )
        )
        payload = _investment_account_payload(data)
        account_id = str((payload.get("account") or {}).get("id") or "")
        if not account_id:
            raise APIError("Investment account creation did not return an account ID.")

        if not in_net_worth:
            run_api_call(
                lambda: client.update_account(
                    account_id=account_id,
                    include_in_net_worth=False,
                )
            )

        after: Any = run_api_call(lambda: client.get_accounts())
        created = next(
            (
                account
                for account in after.get("accounts", [])
                if str(account.get("id")) == account_id
            ),
            None,
        )
        if created is None:
            raise APIError(
                "Created investment account was absent from exact account readback.",
                details={"account_id": account_id},
            )
        mismatches: dict[str, Any] = {}
        if created.get("isManual") is not True:
            mismatches["isManual"] = created.get("isManual")
        if created.get("manualInvestmentsTrackingMethod") != "holdings":
            mismatches["manualInvestmentsTrackingMethod"] = created.get(
                "manualInvestmentsTrackingMethod"
            )
        if not in_net_worth and (
            created.get("includeInNetWorth") is not False
            or created.get("includeBalanceInNetWorth") is not False
        ):
            mismatches["netWorth"] = {
                "includeInNetWorth": created.get("includeInNetWorth"),
                "includeBalanceInNetWorth": created.get("includeBalanceInNetWorth"),
            }
        if created.get("holdingsCount") != len(initial_holdings):
            mismatches["holdingsCount"] = {
                "expected": len(initial_holdings),
                "actual": created.get("holdingsCount"),
            }
        if mismatches:
            raise APIError(
                "Investment account creation did not survive exact readback.",
                details={"account_id": account_id, "mismatches": mismatches},
            )

    output(
        {
            "status": "created",
            "entity": "investment_account",
            "id": account_id,
            "verified": True,
            "initial_holding_count": len(initial_holdings),
            "account": created,
        },
        _resolve_format(format, json_output),
    )


@app.command("clone-filtered")
@handle_errors
def clone_filtered(
    source_account_id: Annotated[str, typer.Argument(help="Source account ID to clone")],
    name: Annotated[str, typer.Option("--name", help="New manual account name")],
    target_account: Annotated[
        str | None,
        typer.Option(
            "--target-account",
            help="Existing manual destination account ID to reuse.",
        ),
    ] = None,
    normalization_csv: Annotated[
        Path | None,
        typer.Option(
            "--normalization-csv",
            help=(
                "CSV overrides with source_transaction_id, amount, and optional "
                "category_id/notes columns."
            ),
        ),
    ] = None,
    min_interest_amount: Annotated[
        float,
        typer.Option(
            "--min-interest-amount",
            min=0,
            help="Minimum absolute USD interest amount to keep for brokerage clones.",
        ),
    ] = 10.0,
    min_other_amount: Annotated[
        float,
        typer.Option(
            "--min-other-amount",
            min=0,
            help="Minimum absolute USD amount for non-trade brokerage activity.",
        ),
    ] = 10.0,
    max_writes: Annotated[
        int | None,
        typer.Option(
            "--max-writes",
            min=1,
            help="Maximum new brokerage transactions to create in one run.",
        ),
    ] = None,
    exclude_category: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude-category",
            help="Exact category names to exclude. Repeatable.",
        ),
    ] = None,
    exclude_regex: Annotated[
        str,
        typer.Option(
            "--exclude-regex",
            help="Regex over plaid/merchant/display text for rows to exclude.",
        ),
    ] = r"(?!)",
    include_in_net_worth: Annotated[
        bool | None,
        typer.Option(
            "--include-in-net-worth/--exclude-from-net-worth",
            help=(
                "Include the cloned manual account in net worth. Brokerage mirrors "
                "default to excluded; other clones default to included."
            ),
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the clone without creating anything."),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a manual clone of an account while filtering noisy transactions.

    Brokerage clones preserve balance history while replaying trades and material
    activity as balance-neutral manual transactions. Existing destinations are
    reused by explicit ID or unique exact name, making retries idempotent.
    """
    output_format = _resolve_format(format, json_output)
    exclude_category_names = set(exclude_category or ["FX Conversion"])
    exclude_pattern = re.compile(exclude_regex)
    min_interest = Decimal(str(min_interest_amount))
    min_other = Decimal(str(min_other_amount))
    overrides = _load_normalization_overrides(normalization_csv)

    with spinner("Preparing filtered account clone..."):
        client = get_authenticated_client()
        raw_accounts: Any = run_api_call(lambda: client.get_accounts())
        accounts = raw_accounts.get("accounts", [])
        source_account = _find_account(accounts, source_account_id)
        if source_account is None:
            raise typer.BadParameter(f"Account {source_account_id} not found.")
        account_type, account_subtype = _source_account_type_names(source_account)
        is_brokerage = _should_clone_via_history(source_account)
        current_balance = Decimal(str(source_account.get("currentBalance") or 0))

    if not account_type or not account_subtype:
        raise typer.BadParameter(
            "Source account is missing raw type/subtype names required for manual clone."
        )

    if is_brokerage:
        resolved_target = _resolve_clone_target(
            accounts,
            source_account_id=source_account_id,
            target_account_id=target_account,
            target_name=name,
        )
        source_transactions = _fetch_all_account_transactions(client, source_account_id)
        brokerage_kept, brokerage_excluded = _prepare_brokerage_ledger(
            source_transactions,
            overrides=overrides,
            exclude_category_names=exclude_category_names,
            exclude_pattern=exclude_pattern,
            min_interest_amount=min_interest,
            min_other_amount=min_other,
        )
        target_account_id = str(resolved_target.get("id")) if resolved_target else None
        summary: dict[str, Any] = {
            "status": "dry_run" if dry_run else "created",
            "entity": "account_clone",
            "clone_mode": "brokerage_ledger",
            "source_account_id": source_account_id,
            "source_account_name": source_account.get("displayName"),
            "target_account_name": name,
            "target_account_id": target_account_id,
            "target_account_status": "existing" if resolved_target else "new",
            "source_account_type": account_type,
            "source_account_subtype": account_subtype,
            "source_current_balance": float(current_balance),
            "target_current_balance": (
                float(Decimal(str(resolved_target.get("currentBalance") or 0)))
                if resolved_target
                else float(current_balance)
            ),
            "kept_transaction_count": len(brokerage_kept),
            "excluded_transaction_count": len(brokerage_excluded),
            "normalized_transaction_count": sum(
                row["normalization_source"] != "source" for row in brokerage_kept
            ),
            "min_interest_amount": float(min_interest),
            "min_other_amount": float(min_other),
            "max_writes": max_writes,
            "exclude_categories": sorted(exclude_category_names),
            "exclude_regex": exclude_regex,
            "normalization_csv": str(normalization_csv) if normalization_csv else None,
            "kept_transactions": [_ledger_summary_row(row) for row in brokerage_kept],
            "excluded_reason_counts": {
                reason: sum(row["reason"] == reason for row in brokerage_excluded)
                for reason in sorted({row["reason"] for row in brokerage_excluded})
            },
            "excluded_examples": [_ledger_summary_row(row) for row in brokerage_excluded[:20]],
            "limitations": [
                "Manual brokerage accounts copy transaction history and balance snapshots, "
                "not live security holdings."
            ],
        }

        if dry_run:
            output(summary, output_format)
            return

        with spinner("Fetching source balance history..."):
            source_history_rows = _fetch_account_history_rows(client, source_account_id)
        upload_rows = _balance_history_rows(source_account, source_history_rows)
        balance_history_sync_required = bool(upload_rows) and resolved_target is None
        if resolved_target is not None:
            with spinner("Comparing target balance history..."):
                target_history_rows = _fetch_account_history_rows(
                    client, str(resolved_target.get("id"))
                )
            target_balance = Decimal(str(resolved_target.get("currentBalance") or 0))
            balance_history_sync_required = target_balance != current_balance or _history_signature(
                target_history_rows
            ) != _history_signature(source_history_rows)

        uploaded_history_rows = 0
        if resolved_target is None:
            with spinner("Creating filtered manual account..."):
                created_brokerage_account: Any = run_api_call(
                    lambda: client.create_manual_account(
                        account_type=account_type,
                        account_sub_type=account_subtype,
                        is_in_net_worth=(
                            False if include_in_net_worth is None else include_in_net_worth
                        ),
                        account_name=name,
                        account_balance=float(current_balance),
                    )
                )
            target_account_id = extract_id(
                created_brokerage_account, ("createManualAccount", "account")
            )
            if not target_account_id:
                raise RuntimeError("Manual account create did not return a target account ID.")

        if balance_history_sync_required:
            if not upload_rows:
                raise RuntimeError(
                    "Target balance differs but the source returned no uploadable history rows."
                )
            with spinner("Uploading mirrored balance history..."):
                upload_success: bool = run_api_call(
                    lambda: client.upload_account_balance_history(
                        account_id=str(target_account_id),
                        csv_content=upload_rows,
                        timeout=300,
                        delay=10,
                    ),
                    timeout_seconds=310,
                    max_retries=0,
                )
            if not upload_success:
                raise RuntimeError("Balance history upload did not complete successfully.")
            uploaded_history_rows = len(upload_rows)

        target_transactions = _fetch_all_account_transactions(client, str(target_account_id))
        target_clones = _index_target_clones(target_transactions)

        brokerage_created_transaction_ids: list[str] = []
        brokerage_existing_transaction_ids: list[str] = []
        brokerage_updated_transaction_ids: list[str] = []
        brokerage_drifted_transactions: list[dict[str, Any]] = []
        processed_transaction_count = 0
        live_write_count = 0
        for prepared in brokerage_kept:
            category_id = prepared["category_id"]
            if not category_id:
                raise RuntimeError(
                    f"Transaction {prepared['source_id']} missing target category ID."
                )
            source_txn = prepared["source"]
            existing_clone = target_clones.get(prepared["source_id"])
            if existing_clone is not None:
                existing_id = str(existing_clone.get("id"))
                brokerage_existing_transaction_ids.append(existing_id)
                drift_fields = _target_clone_drift_fields(prepared, existing_clone)
                if drift_fields:
                    if max_writes is not None and live_write_count >= max_writes:
                        brokerage_existing_transaction_ids.pop()
                        break
                    changes = {
                        "amount": float(prepared["amount"]),
                        "merchant_name": _source_description(source_txn),
                        "category_id": category_id,
                        "notes": prepared["notes"],
                        "date": str(source_txn.get("date")),
                    }
                    run_api_call(
                        partial(
                            client.update_transaction,
                            transaction_id=existing_id,
                            **changes,
                        )
                    )
                    exact_raw: Any = run_api_call(
                        partial(
                            client.get_transaction_details,
                            transaction_id=existing_id,
                            redirect_posted=True,
                        )
                    )
                    exact_txn = exact_raw.get("transaction") or exact_raw
                    remaining_drift = _target_clone_drift_fields(prepared, exact_txn)
                    if remaining_drift:
                        raise RuntimeError(
                            f"Target transaction {existing_id} verification failed for fields: "
                            + ", ".join(remaining_drift)
                        )
                    brokerage_updated_transaction_ids.append(existing_id)
                    live_write_count += 1
                    brokerage_drifted_transactions.append(
                        {
                            "source_transaction_id": prepared["source_id"],
                            "target_transaction_id": existing_id,
                            "fields": drift_fields,
                            "status": "updated",
                        }
                    )
                processed_transaction_count += 1
                continue
            if max_writes is not None and live_write_count >= max_writes:
                break
            result = _create_or_get_transaction(
                date_value=str(source_txn.get("date")),
                account=str(target_account_id),
                amount=float(prepared["amount"]),
                merchant=_source_description(source_txn),
                category=category_id,
                notes=prepared["notes"],
                update_balance=False,
                tag_ids=[],
                dedupe_fields=["date", "amount", "category", "merchant", "notes"],
                client=client,
            )
            result_id = str(result.get("id"))
            if result.get("status") == "existing":
                brokerage_existing_transaction_ids.append(result_id)
            else:
                brokerage_created_transaction_ids.append(result_id)
                live_write_count += 1
            processed_transaction_count += 1

        deferred_transaction_count = len(brokerage_kept) - processed_transaction_count

        balance_restored = False
        if resolved_target is not None:
            final_accounts_raw: Any = run_api_call(lambda: client.get_accounts())
            final_target = _find_account(
                final_accounts_raw.get("accounts", []), str(target_account_id)
            )
            if final_target is None:
                raise RuntimeError(f"Target account {target_account_id} disappeared after sync.")
            final_balance = Decimal(str(final_target.get("currentBalance") or 0))
            if final_balance != current_balance:
                run_api_call(
                    lambda: client.update_account(
                        account_id=str(target_account_id),
                        account_balance=float(current_balance),
                    )
                )
                verified_accounts_raw: Any = run_api_call(lambda: client.get_accounts())
                verified_target = _find_account(
                    verified_accounts_raw.get("accounts", []), str(target_account_id)
                )
                verified_balance = Decimal(str((verified_target or {}).get("currentBalance") or 0))
                if verified_balance != current_balance:
                    raise RuntimeError(
                        f"Target account balance verification failed: expected "
                        f"{current_balance}, got {verified_balance}."
                    )
                balance_restored = True

        summary.update(
            {
                "status": (
                    "partial"
                    if deferred_transaction_count
                    else ("populated" if resolved_target else "created")
                ),
                "id": target_account_id,
                "target_account_id": target_account_id,
                "balance_history_sync_required": balance_history_sync_required,
                "source_history_rows": len(source_history_rows),
                "uploaded_history_rows": uploaded_history_rows,
                "created_transaction_count": len(brokerage_created_transaction_ids),
                "existing_transaction_count": len(brokerage_existing_transaction_ids),
                "updated_transaction_count": len(brokerage_updated_transaction_ids),
                "drifted_transaction_count": len(brokerage_drifted_transactions),
                "drifted_transactions": brokerage_drifted_transactions,
                "live_write_count": live_write_count,
                "target_balance_restored": balance_restored,
                "processed_transaction_count": processed_transaction_count,
                "deferred_transaction_count": deferred_transaction_count,
                "created_transaction_ids": brokerage_created_transaction_ids,
                "existing_transaction_ids": brokerage_existing_transaction_ids,
                "updated_transaction_ids": brokerage_updated_transaction_ids,
            }
        )
        output(summary, output_format)
        return

    source_transactions = _fetch_all_account_transactions(client, source_account_id)
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for txn in source_transactions:
        should_exclude = _should_exclude_transaction(
            txn,
            exclude_category_names=exclude_category_names,
            exclude_pattern=exclude_pattern,
        ) or (
            _is_interest_transaction(txn)
            and abs(Decimal(str(txn.get("amount") or 0))) < min_interest
        )
        (excluded if should_exclude else kept).append(txn)

    kept.sort(key=lambda txn: (txn.get("date") or "", str(txn.get("id") or "")))
    kept_total = sum(Decimal(str(txn.get("amount") or 0)) for txn in kept)
    opening_balance = current_balance - kept_total

    summary = {
        "status": "dry_run" if dry_run else "created",
        "entity": "account_clone",
        "clone_mode": "transaction_replay",
        "source_account_id": source_account_id,
        "source_account_name": source_account.get("displayName"),
        "target_account_name": name,
        "source_account_type": account_type,
        "source_account_subtype": account_subtype,
        "source_current_balance": float(current_balance),
        "opening_balance": float(opening_balance),
        "kept_transaction_count": len(kept),
        "excluded_transaction_count": len(excluded),
        "exclude_categories": sorted(exclude_category_names),
        "exclude_regex": exclude_regex,
        "excluded_examples": [
            {
                "id": txn.get("id"),
                "date": txn.get("date"),
                "amount": txn.get("amount"),
                "description": _source_description(txn),
            }
            for txn in excluded[:10]
        ],
    }

    if dry_run:
        output(summary, output_format)
        return

    with spinner("Creating filtered manual account..."):
        created_account: Any = run_api_call(
            lambda: client.create_manual_account(
                account_type=account_type,
                account_sub_type=account_subtype,
                is_in_net_worth=True if include_in_net_worth is None else include_in_net_worth,
                account_name=name,
                account_balance=float(opening_balance),
            )
        )
    target_account_id = extract_id(created_account, ("createManualAccount", "account"))
    if not target_account_id:
        raise RuntimeError("Manual account create did not return a target account ID.")

    created_transaction_ids: list[str] = []
    for txn in kept:
        category = txn.get("category") or {}
        category_id = category.get("id")
        if not category_id:
            raise RuntimeError(f"Transaction {txn.get('id')} missing category ID.")
        result = _create_or_get_transaction(
            date_value=str(txn.get("date")),
            account=str(target_account_id),
            amount=float(txn.get("amount") or 0),
            merchant=_source_description(txn),
            category=str(category_id),
            notes=str(txn.get("notes") or ""),
            update_balance=True,
            tag_ids=[],
            dedupe_fields=["date", "amount", "category", "merchant", "notes"],
            client=client,
        )
        created_transaction_ids.append(str(result.get("id")))

    summary.update(
        {
            "id": target_account_id,
            "target_account_id": target_account_id,
            "created_transaction_count": len(created_transaction_ids),
            "created_transaction_ids_sample": created_transaction_ids[:20],
        }
    )
    output(summary, output_format)


@app.command("update")
@handle_errors
def update(
    account_id: Annotated[str, typer.Argument(help="Account ID to update")],
    name: Annotated[str | None, typer.Option("--name", help="New account name")] = None,
    balance: Annotated[float | None, typer.Option("--balance", help="New account balance")] = None,
    account_type: Annotated[str | None, typer.Option("--type", help="New account type")] = None,
    subtype: Annotated[str | None, typer.Option("--subtype", help="New account subtype")] = None,
    include_in_net_worth: Annotated[
        bool | None,
        typer.Option("--include-in-net-worth/--exclude-from-net-worth"),
    ] = None,
    hide_from_summary_list: Annotated[
        bool | None,
        typer.Option("--hide-from-summary/--show-in-summary"),
    ] = None,
    hide_transactions_from_reports: Annotated[
        bool | None,
        typer.Option("--hide-transactions-from-reports/--show-transactions-in-reports"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Rename or update account metadata, balance, type, and visibility."""
    changes: dict[str, Any] = {}
    if name is not None:
        changes["account_name"] = name
    if balance is not None:
        changes["account_balance"] = balance
    if account_type is not None:
        changes["account_type"] = account_type
    if subtype is not None:
        changes["account_sub_type"] = subtype
    if include_in_net_worth is not None:
        changes["include_in_net_worth"] = include_in_net_worth
    if hide_from_summary_list is not None:
        changes["hide_from_summary_list"] = hide_from_summary_list
    if hide_transactions_from_reports is not None:
        changes["hide_transactions_from_reports"] = hide_transactions_from_reports

    if not changes:
        output(
            {"status": "error", "entity": "account", "message": "No account changes specified."},
            _resolve_format(format, json_output),
        )
        raise typer.Exit(1)

    with spinner("Updating account..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.update_account(account_id=account_id, **changes))
    output(
        mutation_result(
            status="updated",
            entity="account",
            id=account_id,
            changes=changes,
            result=data,
        ),
        _resolve_format(format, json_output),
    )


@app.command("delete")
@handle_errors
def delete(
    account_id: Annotated[str, typer.Argument(help="Account ID to delete")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm account deletion")] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Delete an account."""
    if not yes:
        output(
            {"status": "error", "entity": "account", "message": "Account delete requires --yes."},
            _resolve_format(format, json_output),
        )
        raise typer.Exit(1)

    with spinner("Deleting account..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.delete_account(account_id=account_id))
    output(
        mutation_result(
            status="deleted",
            entity="account",
            id=account_id,
            account_id=account_id,
            result=data,
        ),
        _resolve_format(format, json_output),
    )


def _read_balance_history_csv(path: Path) -> list[BalanceHistoryRow]:
    """Read Monarch balance history rows from CSV."""
    rows: list[BalanceHistoryRow] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = {
                key.strip().lower().replace(" ", "_"): value for key, value in row.items()
            }
            date_text = normalized.get("date")
            amount_text = normalized.get("amount") or normalized.get("balance")
            if not date_text or amount_text is None:
                raise typer.BadParameter("CSV must include date and amount columns.")
            rows.append(
                BalanceHistoryRow(
                    date=datetime.fromisoformat(date_text),
                    amount=float(amount_text),
                    account_name=normalized.get("account_name"),
                )
            )
    return rows


@app.command("upload-history")
@handle_errors
def upload_history(
    account_id: Annotated[str, typer.Argument(help="Account ID")],
    csv_path: Annotated[
        Path,
        typer.Argument(
            help="CSV with date, amount, and optional account_name columns",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    timeout: Annotated[int, typer.Option("--timeout", help="Upload timeout seconds")] = 300,
    delay: Annotated[int, typer.Option("--delay", help="Polling delay seconds")] = 10,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Upload historical balance CSV data."""
    rows = _read_balance_history_csv(csv_path)
    with spinner("Uploading balance history..."):
        client = get_authenticated_client()
        success: bool = run_api_call(
            lambda: client.upload_account_balance_history(
                account_id=account_id,
                csv_content=rows,
                timeout=timeout,
                delay=delay,
            ),
            timeout_seconds=timeout + delay,
            max_retries=0,
        )
    output(
        mutation_result(
            status="uploaded" if success else "failed",
            entity="account",
            id=account_id,
            account_id=account_id,
            rows=len(rows),
            result=success,
        ),
        _resolve_format(format, json_output),
    )
