"""Transaction commands for Monarch CLI."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call, run_async
from ..core.dates import DatePreset, parse_date_range
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.transactions import transform_transaction, transform_transactions
from ._mutation import extract_id, mutation_result

app = typer.Typer(
    help="Transaction management",
    no_args_is_help=True,
)

tags_app = typer.Typer(help="Transaction tag management", no_args_is_help=True)
splits_app = typer.Typer(help="Transaction split management", no_args_is_help=True)

DEFAULT_DEDUPE_KEY = "date,amount,category,notes"
SUPPORTED_DEDUPE_FIELDS = {"date", "amount", "account", "category", "merchant", "notes"}


def _parse_date(date_str: str | None) -> date | None:
    """Parse a date string in YYYY-MM-DD format.

    Args:
        date_str: Date string in YYYY-MM-DD format, or None.

    Returns:
        Parsed date object, or None if input was None.

    Raises:
        typer.BadParameter: If date string is not valid YYYY-MM-DD format.
    """
    if date_str is None:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError as e:
        raise typer.BadParameter(
            f"Invalid date format: '{date_str}'. Use YYYY-MM-DD format."
        ) from e


def _parse_dedupe_key(dedupe_key: str | None) -> list[str]:
    """Parse and validate comma-separated dedupe key fields."""
    if dedupe_key is None or not dedupe_key.strip():
        return []

    fields = [field.strip() for field in dedupe_key.split(",") if field.strip()]
    unsupported = [field for field in fields if field not in SUPPORTED_DEDUPE_FIELDS]
    if unsupported:
        supported = ", ".join(sorted(SUPPORTED_DEDUPE_FIELDS))
        raise typer.BadParameter(
            f"Unsupported dedupe field(s): {', '.join(unsupported)}. Supported: {supported}."
        )
    return fields


def _extract_created_transaction_id(raw: Any) -> str | None:
    """Extract a transaction ID from common create/upstream response shapes."""
    if not isinstance(raw, dict):
        return None
    if raw.get("id"):
        return str(raw["id"])

    create_payload = raw.get("createTransaction")
    if isinstance(create_payload, dict):
        transaction = create_payload.get("transaction")
        if isinstance(transaction, dict) and transaction.get("id"):
            return str(transaction["id"])

    transaction = raw.get("transaction")
    if isinstance(transaction, dict) and transaction.get("id"):
        return str(transaction["id"])

    return None


def _unwrap_transaction(raw: Any) -> dict[str, Any]:
    """Return the transaction object from detail or raw transaction responses."""
    if not isinstance(raw, dict):
        return {}
    transaction = raw.get("getTransaction")
    if isinstance(transaction, dict):
        return transaction
    transaction = raw.get("transaction")
    if isinstance(transaction, dict):
        return transaction
    return raw


def _normalized_transaction(
    raw: Any,
    *,
    transaction_id: str,
    date_value: str,
    account: str,
    amount: float,
    merchant: str,
    category: str,
    notes: str,
) -> dict[str, Any]:
    """Normalize a readback transaction and fill fields the API omits for manual rows."""
    normalized = transform_transaction(_unwrap_transaction(raw))
    fallbacks: dict[str, Any] = {
        "id": transaction_id,
        "date": date_value,
        "amount": amount,
        "description": merchant,
        "category_id": category,
        "account_id": account,
        "notes": notes,
    }
    for key, value in fallbacks.items():
        if normalized.get(key) in (None, ""):
            normalized[key] = value
    return normalized


def _dedupe_value_matches(
    transaction: dict[str, Any],
    field: str,
    *,
    date_value: str,
    account: str,
    amount: float,
    merchant: str,
    category: str,
    notes: str,
) -> bool:
    """Compare one dedupe field against a normalized transaction."""
    if field == "date":
        return transaction.get("date") == date_value
    if field == "amount":
        transaction_amount = transaction.get("amount")
        if transaction_amount is None:
            return False
        try:
            return round(float(transaction_amount), 2) == round(amount, 2)
        except (TypeError, ValueError):
            return False
    if field == "account":
        return transaction.get("account_id") == account
    if field == "category":
        return transaction.get("category_id") == category
    if field == "merchant":
        return (transaction.get("description") or "") == merchant
    if field == "notes":
        return (transaction.get("notes") or "") == notes
    return False


def _matches_dedupe_key(
    transaction: dict[str, Any],
    dedupe_fields: list[str],
    *,
    date_value: str,
    account: str,
    amount: float,
    merchant: str,
    category: str,
    notes: str,
) -> bool:
    """Return whether a transaction matches every requested dedupe field."""
    return all(
        _dedupe_value_matches(
            transaction,
            field,
            date_value=date_value,
            account=account,
            amount=amount,
            merchant=merchant,
            category=category,
            notes=notes,
        )
        for field in dedupe_fields
    )


def _format_create_result(
    *,
    status: str,
    transaction: dict[str, Any],
    tag_ids: list[str],
    dedupe_key: list[str],
) -> dict[str, Any]:
    """Build stable write-command output with the ID at top level."""
    return {
        "id": transaction.get("id"),
        "status": status,
        "entity": "transaction",
        "date": transaction.get("date"),
        "amount": transaction.get("amount"),
        "description": transaction.get("description"),
        "category": transaction.get("category"),
        "category_id": transaction.get("category_id"),
        "account": transaction.get("account"),
        "account_id": transaction.get("account_id"),
        "is_pending": transaction.get("is_pending"),
        "notes": transaction.get("notes"),
        "tag_ids": tag_ids,
        "dedupe_key": dedupe_key,
        "transaction": transaction,
    }


def _create_or_get_transaction(
    *,
    date_value: str,
    account: str,
    amount: float,
    merchant: str,
    category: str,
    notes: str,
    update_balance: bool,
    tag_ids: list[str],
    dedupe_fields: list[str],
) -> dict[str, Any]:
    """Create a manual transaction, optionally returning a matching existing row first."""
    client = get_authenticated_client()

    if dedupe_fields:
        raw_existing = run_api_call(
            lambda: client.get_transactions(
                limit=500,
                offset=0,
                start_date=date_value,
                end_date=date_value,
                search="",
                category_ids=[category],
                account_ids=[account],
                tag_ids=[],
            )
        )
        for existing in transform_transactions(raw_existing):
            if _matches_dedupe_key(
                existing,
                dedupe_fields,
                date_value=date_value,
                account=account,
                amount=amount,
                merchant=merchant,
                category=category,
                notes=notes,
            ):
                if tag_ids:
                    existing_id = str(existing["id"])
                    run_api_call(
                        partial(
                            client.set_transaction_tags,
                            transaction_id=existing_id,
                            tag_ids=tag_ids,
                        )
                    )
                return _format_create_result(
                    status="existing",
                    transaction=existing,
                    tag_ids=tag_ids,
                    dedupe_key=dedupe_fields,
                )

    raw_created = run_api_call(
        lambda: client.create_transaction(
            date=date_value,
            account_id=account,
            amount=amount,
            merchant_name=merchant,
            category_id=category,
            notes=notes,
            update_balance=update_balance,
        )
    )
    transaction_id = _extract_created_transaction_id(raw_created)
    if transaction_id is None:
        raise ValueError("Create response did not include a transaction ID")

    if tag_ids:
        run_api_call(
            lambda: client.set_transaction_tags(
                transaction_id=transaction_id,
                tag_ids=tag_ids,
            )
        )

    raw_details = run_api_call(
        lambda: client.get_transaction_details(
            transaction_id=transaction_id,
            redirect_posted=False,
        )
    )
    transaction = _normalized_transaction(
        raw_details,
        transaction_id=transaction_id,
        date_value=date_value,
        account=account,
        amount=amount,
        merchant=merchant,
        category=category,
        notes=notes,
    )
    return _format_create_result(
        status="created",
        transaction=transaction,
        tag_ids=tag_ids,
        dedupe_key=dedupe_fields,
    )


@app.command("list")
@handle_errors
def list_cmd(
    limit: Annotated[
        int,
        typer.Option(
            "-l",
            "--limit",
            help="Maximum number of transactions to return (API default: 100)",
        ),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option(
            "-o",
            "--offset",
            help="Number of transactions to skip (for pagination)",
        ),
    ] = 0,
    start: Annotated[
        str | None,
        typer.Option(
            "-s",
            "--start",
            help="Start date filter (YYYY-MM-DD)",
        ),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option(
            "-e",
            "--end",
            help="End date filter (YYYY-MM-DD)",
        ),
    ] = None,
    preset: Annotated[
        DatePreset | None,
        typer.Option(
            "-p",
            "--preset",
            help="Date range preset (e.g., this-month, last-30-days)",
        ),
    ] = None,
    account: Annotated[
        list[str] | None,
        typer.Option(
            "-a",
            "--account",
            help="Filter by account ID (repeatable)",
        ),
    ] = None,
    category: Annotated[
        list[str] | None,
        typer.Option(
            "-c",
            "--category",
            help="Filter by category ID (repeatable)",
        ),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option(
            "-t",
            "--tag",
            help="Filter by transaction tag ID (repeatable)",
        ),
    ] = None,
    search: Annotated[
        str | None,
        typer.Option(
            "--search",
            help="Search term for transaction description/merchant",
        ),
    ] = None,
    has_attachments: Annotated[
        bool | None,
        typer.Option("--has-attachments/--missing-attachments"),
    ] = None,
    has_notes: Annotated[
        bool | None,
        typer.Option("--has-notes/--missing-notes"),
    ] = None,
    hidden_from_reports: Annotated[
        bool | None,
        typer.Option("--hidden-from-reports/--visible-in-reports"),
    ] = None,
    is_split: Annotated[
        bool | None,
        typer.Option("--is-split/--not-split"),
    ] = None,
    is_recurring: Annotated[
        bool | None,
        typer.Option("--is-recurring/--not-recurring"),
    ] = None,
    imported_from_mint: Annotated[
        bool | None,
        typer.Option("--imported-from-mint/--not-imported-from-mint"),
    ] = None,
    synced_from_institution: Annotated[
        bool | None,
        typer.Option("--synced-from-institution/--not-synced-from-institution"),
    ] = None,
    needs_review: Annotated[
        bool | None,
        typer.Option("--needs-review/--reviewed"),
    ] = None,
    visibility: Annotated[
        str | None,
        typer.Option(
            "--visibility",
            help="Transaction visibility: hidden_transactions_only or all_transactions",
        ),
    ] = None,
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
    """List transactions with filters.

    Fetches transactions from your linked accounts. Supports date filtering
    via explicit dates or presets, account filtering, and text search.

    Examples:
        monarch transactions list                      # Recent transactions
        monarch transactions list --limit 20           # Last 20 transactions
        monarch transactions list --preset this-month  # This month's transactions
        monarch transactions list -s 2024-01-01 -e 2024-01-31  # Date range
        monarch transactions list --account ACC123     # Specific account
        monarch transactions list --search "coffee"    # Search by text
        monarch transactions list | jq .              # Auto-JSON when piped
    """
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON
    if ndjson:
        output_format = OutputFormat.COMPACT  # Will handle NDJSON below

    # Parse date range (preset + explicit dates)
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    start_str, end_str = parse_date_range(preset, start_date, end_date)

    # Prepare account IDs
    account_ids = list(account) if account else []
    category_ids = list(category) if category else []
    tag_ids = list(tag) if tag else []

    with spinner("Fetching transactions..."):
        client = get_authenticated_client()
        raw_data: Any = run_api_call(
            lambda: client.get_transactions(
                limit=limit,
                offset=offset,
                start_date=start_str,
                end_date=end_str,
                search=search or "",
                category_ids=category_ids,
                account_ids=account_ids,
                tag_ids=tag_ids,
                has_attachments=has_attachments,
                has_notes=has_notes,
                hidden_from_reports=hidden_from_reports,
                is_split=is_split,
                is_recurring=is_recurring,
                imported_from_mint=imported_from_mint,
                synced_from_institution=synced_from_institution,
                needs_review=needs_review,
                transaction_visibility=visibility,
            )
        )

        # Transform unless raw mode
        data = raw_data if raw else transform_transactions(raw_data)

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
def update(
    transaction_id: Annotated[
        str,
        typer.Argument(help="Transaction ID to update"),
    ],
    amount: Annotated[
        float | None,
        typer.Option(
            "--amount",
            help="New transaction amount",
        ),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option(
            "--description",
            help="New merchant/description name",
        ),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option(
            "--category",
            help="Category ID to assign",
        ),
    ] = None,
    notes: Annotated[
        str | None,
        typer.Option(
            "--notes",
            help="Notes to add to transaction",
        ),
    ] = None,
    date_value: Annotated[
        str | None,
        typer.Option(
            "--date",
            help="New transaction date (YYYY-MM-DD)",
        ),
    ] = None,
    goal: Annotated[
        str | None,
        typer.Option(
            "--goal",
            help="Goal ID to assign",
        ),
    ] = None,
    hide_from_reports: Annotated[
        bool | None,
        typer.Option(
            "--hide-from-reports/--show-in-reports",
            help="Hide or show transaction in reports",
        ),
    ] = None,
    needs_review: Annotated[
        bool | None,
        typer.Option(
            "--needs-review/--clear-review",
            help="Mark transaction as needing review or reviewed",
        ),
    ] = None,
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
            help="Output as JSON",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be changed without applying",
        ),
    ] = False,
) -> None:
    """Update a transaction's properties.

    Modify amount, description, category, notes, or date for a transaction.
    Use --dry-run to preview changes without applying them.

    Examples:
        monarch transactions update TXN123 --amount 25.50
        monarch transactions update TXN123 --description "Coffee Shop"
        monarch transactions update TXN123 --category CAT456
        monarch transactions update TXN123 --notes "Business lunch"
        monarch transactions update TXN123 --dry-run --amount 30.00
    """
    output_format = OutputFormat.JSON if json_output else format

    # Collect changes
    changes: dict[str, Any] = {}

    if amount is not None:
        changes["amount"] = amount
    if description is not None:
        changes["merchant_name"] = description
    if category is not None:
        changes["category_id"] = category
    if notes is not None:
        changes["notes"] = notes
    if date_value is not None:
        changes["date"] = date_value
    if goal is not None:
        changes["goal_id"] = goal
    if hide_from_reports is not None:
        changes["hide_from_reports"] = hide_from_reports
    if needs_review is not None:
        changes["needs_review"] = needs_review

    # Require at least one change
    if not changes:
        output(
            {
                "status": "error",
                "transaction_id": transaction_id,
                "message": "No changes specified. "
                "Use --amount, --description, --category, --notes, --date, --goal, "
                "--hide-from-reports, or --needs-review.",
            },
            output_format,
        )
        raise typer.Exit(1)

    # Dry run mode
    if dry_run:
        output(
            {
                "status": "dry_run",
                "transaction_id": transaction_id,
                "changes": changes,
                "message": "No changes applied (dry run mode)",
            },
            output_format,
        )
        return

    # Apply the update
    with spinner("Updating transaction..."):
        client = get_authenticated_client()
        run_api_call(lambda: client.update_transaction(transaction_id=transaction_id, **changes))

    output(
        {
            "id": transaction_id,
            "status": "updated",
            "entity": "transaction",
            "transaction_id": transaction_id,
            "changes": changes,
        },
        output_format,
    )


@app.command("create")
@handle_errors
def create(
    date_value: Annotated[str, typer.Option("--date", help="Transaction date (YYYY-MM-DD)")],
    account: Annotated[str, typer.Option("-a", "--account", help="Account ID")],
    amount: Annotated[float, typer.Option("--amount", help="Transaction amount")],
    merchant: Annotated[str, typer.Option("--merchant", help="Merchant name")],
    category: Annotated[str, typer.Option("-c", "--category", help="Category ID")],
    notes: Annotated[str, typer.Option("--notes", help="Transaction notes")] = "",
    tag: Annotated[
        list[str] | None,
        typer.Option("-t", "--tag", help="Tag ID to assign. Repeatable."),
    ] = None,
    dedupe_key: Annotated[
        str | None,
        typer.Option(
            "--dedupe-key",
            help=(
                "Comma-separated fields for idempotent create. "
                "Supported: date, amount, account, category, merchant, notes."
            ),
        ),
    ] = None,
    update_balance: Annotated[
        bool,
        typer.Option("--update-balance", help="Update the manual account balance"),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a manual transaction."""
    output_format = OutputFormat.JSON if json_output else format
    tag_ids = list(tag) if tag else []
    dedupe_fields = _parse_dedupe_key(dedupe_key)

    with spinner("Creating transaction..."):
        data = _create_or_get_transaction(
            date_value=date_value,
            account=account,
            amount=amount,
            merchant=merchant,
            category=category,
            notes=notes,
            update_balance=update_balance,
            tag_ids=tag_ids,
            dedupe_fields=dedupe_fields,
        )
    output(data, output_format)


@app.command("upsert")
@handle_errors
def upsert(
    date_value: Annotated[str, typer.Option("--date", help="Transaction date (YYYY-MM-DD)")],
    account: Annotated[str, typer.Option("-a", "--account", help="Account ID")],
    amount: Annotated[float, typer.Option("--amount", help="Transaction amount")],
    merchant: Annotated[str, typer.Option("--merchant", help="Merchant name")],
    category: Annotated[str, typer.Option("-c", "--category", help="Category ID")],
    notes: Annotated[str, typer.Option("--notes", help="Transaction notes")] = "",
    tag: Annotated[
        list[str] | None,
        typer.Option("-t", "--tag", help="Tag ID to assign. Repeatable."),
    ] = None,
    dedupe_key: Annotated[
        str,
        typer.Option(
            "--dedupe-key",
            help=(
                "Comma-separated fields for idempotent matching. "
                "Supported: date, amount, account, category, merchant, notes."
            ),
        ),
    ] = DEFAULT_DEDUPE_KEY,
    update_balance: Annotated[
        bool,
        typer.Option("--update-balance", help="Update the manual account balance on create"),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a manual transaction unless the dedupe key matches an existing row."""
    output_format = OutputFormat.JSON if json_output else format
    tag_ids = list(tag) if tag else []
    dedupe_fields = _parse_dedupe_key(dedupe_key)
    if not dedupe_fields:
        raise typer.BadParameter("Upsert requires at least one --dedupe-key field.")

    with spinner("Upserting transaction..."):
        data = _create_or_get_transaction(
            date_value=date_value,
            account=account,
            amount=amount,
            merchant=merchant,
            category=category,
            notes=notes,
            update_balance=update_balance,
            tag_ids=tag_ids,
            dedupe_fields=dedupe_fields,
        )
    output(data, output_format)


@app.command("show")
@handle_errors
def show(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    redirect_posted: Annotated[
        bool,
        typer.Option("--redirect-posted/--no-redirect-posted"),
    ] = True,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Fetch full details for one transaction."""
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Fetching transaction details..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.get_transaction_details(
                transaction_id=transaction_id,
                redirect_posted=redirect_posted,
            )
        )
    output(data, output_format)


@app.command("delete")
@handle_errors
def delete(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID to delete")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm transaction deletion")] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Delete a transaction."""
    output_format = OutputFormat.JSON if json_output else format
    if not yes:
        output(
            {
                "status": "error",
                "entity": "transaction",
                "message": "Transaction delete requires --yes.",
            },
            output_format,
        )
        raise typer.Exit(1)

    with spinner("Deleting transaction..."):
        client = get_authenticated_client()
        success: bool = run_api_call(lambda: client.delete_transaction(transaction_id))
    output(
        mutation_result(
            status="deleted" if success else "failed",
            entity="transaction",
            id=transaction_id,
            transaction_id=transaction_id,
            result=success,
        ),
        output_format,
    )


@app.command("duplicates")
@handle_errors
def duplicates(
    start: Annotated[str | None, typer.Option("-s", "--start", help="Start date")] = None,
    end: Annotated[str | None, typer.Option("-e", "--end", help="End date")] = None,
    account: Annotated[
        list[str] | None,
        typer.Option("-a", "--account", help="Account ID filter, repeatable"),
    ] = None,
    page_size: Annotated[int, typer.Option("--page-size", help="Duplicate scan page size")] = 500,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Find duplicate transactions."""
    output_format = OutputFormat.JSON if json_output else format
    account_ids = list(account) if account else None
    with spinner("Finding duplicate transactions..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.find_duplicate_transactions(
                start_date=start,
                end_date=end,
                account_ids=account_ids,
                page_size=page_size,
            )
        )
    output(data, output_format)


@app.command("attach")
@handle_errors
def attach(
    transaction_id: Annotated[
        str,
        typer.Argument(help="Transaction ID to attach the file to"),
    ],
    file_path: Annotated[
        Path,
        typer.Argument(
            help="Receipt or supporting document to upload",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    filename: Annotated[
        str | None,
        typer.Option(
            "--filename",
            help="Filename to store in Monarch (defaults to the local basename)",
        ),
    ] = None,
    notes: Annotated[
        str | None,
        typer.Option(
            "--notes",
            help="Optionally replace the transaction notes after uploading",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be uploaded without applying changes",
        ),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Upload a receipt or attachment to a transaction.

    The command uses Monarch's transaction attachment upload API exposed by
    monarchmoneycommunity. Pass --notes when the receipt upload and note update
    should be verified as one workflow.

    Examples:
        monarch transactions attach TXN123 ./receipt.pdf
        monarch transactions attach TXN123 ./receipt.png --notes "Receipt: dinner, $42.18."
        monarch transactions attach TXN123 ./receipt.pdf --filename vendor-receipt.pdf
    """
    upload_filename = filename or file_path.name
    file_size = file_path.stat().st_size
    output_format = OutputFormat.JSON if json_output else format

    if dry_run:
        output(
            mutation_result(
                status="dry_run",
                entity="transaction_attachment",
                id=transaction_id,
                transaction_id=transaction_id,
                file=str(file_path),
                filename=upload_filename,
                size_bytes=file_size,
                notes=notes,
                message="No attachment uploaded (dry run mode)",
            ),
            output_format,
        )
        return

    file_content = file_path.read_bytes()

    with spinner("Uploading transaction attachment..."):
        client = get_authenticated_client()
        attachment_result = run_api_call(
            lambda: client.upload_attachment(
                transaction_id=transaction_id,
                file_content=file_content,
                filename=upload_filename,
            )
        )
        note_result = None
        if notes is not None:
            note_result = run_api_call(
                lambda: client.update_transaction(
                    transaction_id=transaction_id,
                    notes=notes,
                )
            )

    output(
        mutation_result(
            status="attached",
            entity="transaction_attachment",
            id=transaction_id,
            transaction_id=transaction_id,
            file=str(file_path),
            filename=upload_filename,
            size_bytes=file_size,
            notes_updated=notes is not None,
            attachment_result=attachment_result,
            note_result=note_result,
            result={
                "attachment": attachment_result,
                "note": note_result,
            },
        ),
        output_format,
    )


@app.command("batch-update")
@handle_errors
def batch_update(
    transaction_ids: Annotated[
        list[str] | None,
        typer.Argument(help="Transaction IDs to update"),
    ] = None,
    stdin: Annotated[
        bool,
        typer.Option(
            "--stdin",
            help="Read transaction IDs from stdin (one per line)",
        ),
    ] = False,
    category: Annotated[
        str | None,
        typer.Option(
            "-c",
            "--category",
            help="Category ID to assign to all transactions",
        ),
    ] = None,
    notes: Annotated[
        str | None,
        typer.Option(
            "-n",
            "--notes",
            help="Notes to set on all transactions",
        ),
    ] = None,
    max_concurrency: Annotated[
        int,
        typer.Option(
            "--max-concurrency",
            help="Maximum number of parallel API calls",
        ),
    ] = 4,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview changes without applying them",
        ),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Batch update multiple transactions at once.

    Apply the same changes to multiple transactions efficiently using
    parallel API calls. Transaction IDs can be passed as arguments or
    piped via stdin.

    Examples:
        # Update specific transactions
        monarch transactions batch-update TXN001 TXN002 --category CAT123

        # Pipe IDs from a search
        monarch transactions list --search "Coffee" --quiet | \\
            monarch transactions batch-update --stdin --category CAT456

        # Preview changes first
        monarch transactions batch-update TXN001 TXN002 --category CAT123 --dry-run

        # Set notes on multiple transactions
        monarch transactions batch-update --stdin --notes "Q1 Expenses" < ids.txt
    """
    # Collect transaction IDs
    ids: list[str] = []

    if transaction_ids:
        ids.extend(transaction_ids)

    if stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:  # Skip empty lines
                ids.append(line)
    output_format = OutputFormat.JSON if json_output else format

    # Validate we have IDs to process
    if not ids:
        output(
            {
                "status": "error",
                "entity": "transaction",
                "message": "No transaction IDs provided. Pass IDs as arguments or use --stdin.",
            },
            output_format,
        )
        raise typer.Exit(1)

    # Validate we have at least one change
    changes: dict[str, Any] = {}
    if category is not None:
        changes["category_id"] = category
    if notes is not None:
        changes["notes"] = notes

    if not changes:
        output(
            {
                "status": "error",
                "entity": "transaction",
                "message": "No changes specified. Use --category/-c or --notes/-n.",
            },
            output_format,
        )
        raise typer.Exit(1)

    # Dry run mode - just show what would happen
    if dry_run:
        output(
            mutation_result(
                status="dry_run",
                entity="transaction",
                ids=ids,
                transaction_count=len(ids),
                transaction_ids=ids,
                changes=changes,
                message=f"Would update {len(ids)} transaction(s) (dry run mode)",
            ),
            output_format,
        )
        return

    # Execute batch update
    async def do_batch_update() -> dict[str, Any]:
        """Execute parallel batch updates with concurrency control."""
        from ..core.config import get_config

        config = get_config()
        client = get_authenticated_client()
        semaphore = asyncio.Semaphore(max_concurrency)
        results: list[dict[str, Any]] = []

        async def update_one(txn_id: str) -> dict[str, Any]:
            """Update a single transaction with semaphore and timeout control."""
            async with semaphore:
                try:
                    async with asyncio.timeout(config.timeout_seconds):
                        await client.update_transaction(transaction_id=txn_id, **changes)
                    return {"id": txn_id, "status": "success"}
                except TimeoutError:
                    return {"id": txn_id, "status": "error", "error": "Request timed out"}
                except Exception as e:
                    return {"id": txn_id, "status": "error", "error": str(e)}

        # Run all updates concurrently
        tasks = [update_one(txn_id) for txn_id in ids]
        results = await asyncio.gather(*tasks)

        # Summarize results
        successes = [r for r in results if r["status"] == "success"]
        failures = [r for r in results if r["status"] == "error"]

        return {
            "status": "completed",
            "entity": "transaction",
            "ids": ids,
            "success_count": len(successes),
            "failure_count": len(failures),
            "changes": changes,
            "results": results,
            "failures": failures if failures else None,
        }

    with spinner(f"Updating {len(ids)} transaction(s)..."):
        result = run_async(do_batch_update())

    output(result, output_format)


@tags_app.command("list")
@handle_errors
def tags_list(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List all transaction tags."""
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Fetching transaction tags..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_transaction_tags())
    output(data, output_format)


@tags_app.command("create")
@handle_errors
def tags_create(
    name: Annotated[str, typer.Option("--name", help="Tag name")],
    color: Annotated[str, typer.Option("--color", help="Tag color")],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a transaction tag."""
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Creating transaction tag..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.create_transaction_tag(name=name, color=color))
    tag_id = extract_id(
        data,
        ("createTransactionTag", "transactionTag"),
        ("createTransactionTag", "tag"),
    )
    output(
        mutation_result(
            status="created",
            entity="transaction_tag",
            id=tag_id,
            name=name,
            color=color,
            result=data,
        ),
        output_format,
    )


@tags_app.command("set")
@handle_errors
def tags_set(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    tag: Annotated[
        list[str],
        typer.Option("-t", "--tag", help="Tag ID to assign. Repeatable."),
    ],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Set the exact tag list on a transaction."""
    output_format = OutputFormat.JSON if json_output else format
    tag_ids = list(tag)
    with spinner("Setting transaction tags..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.set_transaction_tags(transaction_id=transaction_id, tag_ids=tag_ids)
        )
    output(
        mutation_result(
            status="updated",
            entity="transaction_tag",
            id=transaction_id,
            transaction_id=transaction_id,
            tag_ids=tag_ids,
            result=data,
        ),
        output_format,
    )


def _extract_tag_ids(details: dict[str, Any]) -> list[str]:
    """Extract tag IDs from common transaction detail response shapes."""
    transaction = (
        details.get("transaction") if isinstance(details.get("transaction"), dict) else details
    )
    raw_tags = transaction.get("tags") if isinstance(transaction, dict) else []
    if not isinstance(raw_tags, list):
        return []
    return [str(tag["id"]) for tag in raw_tags if isinstance(tag, dict) and tag.get("id")]


@tags_app.command("remove")
@handle_errors
def tags_remove(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    tag: Annotated[
        list[str],
        typer.Option("-t", "--tag", help="Tag ID to remove. Repeatable."),
    ],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Remove transaction tags while preserving the remaining tags."""
    output_format = OutputFormat.JSON if json_output else format
    remove_ids = set(tag)
    with spinner("Removing transaction tags..."):
        client = get_authenticated_client()
        details: dict[str, Any] = run_api_call(
            lambda: client.get_transaction_details(transaction_id=transaction_id)
        )
        remaining = [tag_id for tag_id in _extract_tag_ids(details) if tag_id not in remove_ids]
        data: Any = run_api_call(
            lambda: client.set_transaction_tags(transaction_id=transaction_id, tag_ids=remaining)
        )
    output(
        mutation_result(
            status="updated",
            entity="transaction_tag",
            id=transaction_id,
            transaction_id=transaction_id,
            tag_ids=remaining,
            removed_tag_ids=list(remove_ids),
            result=data,
        ),
        output_format,
    )


@tags_app.command("clear")
@handle_errors
def tags_clear(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Remove all tags from a transaction."""
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Clearing transaction tags..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.set_transaction_tags(transaction_id=transaction_id, tag_ids=[])
        )
    output(
        mutation_result(
            status="updated",
            entity="transaction_tag",
            id=transaction_id,
            transaction_id=transaction_id,
            tag_ids=[],
            result=data,
        ),
        output_format,
    )


@splits_app.command("show")
@handle_errors
def splits_show(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Read transaction splits."""
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Fetching transaction splits..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_transaction_splits(transaction_id))
    output(data, output_format)


def _read_split_data(splits_json: str | None, splits_file: Path | None) -> list[dict[str, Any]]:
    """Read split payload from inline JSON or a JSON file."""
    if splits_json is None and splits_file is None:
        raise typer.BadParameter("Provide --splits-json or --splits-file.")
    if splits_json is not None and splits_file is not None:
        raise typer.BadParameter("Use only one of --splits-json or --splits-file.")

    if splits_json is not None:
        raw = splits_json
    else:
        if splits_file is None:
            raise typer.BadParameter("Provide --splits-json or --splits-file.")
        raw = splits_file.read_text()
    data = json.loads(raw)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise typer.BadParameter("Split data must be a JSON array of objects.")
    return data


@splits_app.command("update")
@handle_errors
def splits_update(
    transaction_id: Annotated[str, typer.Argument(help="Transaction ID")],
    splits_json: Annotated[
        str | None,
        typer.Option("--splits-json", help="JSON array of split objects"),
    ] = None,
    splits_file: Annotated[
        Path | None,
        typer.Option(
            "--splits-file",
            help="Path to JSON array of split objects",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Update transaction splits."""
    output_format = OutputFormat.JSON if json_output else format
    split_data = _read_split_data(splits_json, splits_file)
    with spinner("Updating transaction splits..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.update_transaction_splits(
                transaction_id=transaction_id,
                split_data=split_data,
            )
        )
    output(
        mutation_result(
            status="updated",
            entity="transaction_split",
            id=transaction_id,
            transaction_id=transaction_id,
            split_data=split_data,
            result=data,
        ),
        output_format,
    )


app.add_typer(tags_app, name="tags")
app.add_typer(splits_app, name="splits")
