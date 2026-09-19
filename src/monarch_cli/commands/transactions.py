"""Transaction commands for Monarch CLI."""

from __future__ import annotations

import asyncio
import math
import sys
from enum import StrEnum
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range, parse_iso_date, validate_date_ordering
from ..core.error_handler import handle_errors
from ..core.exceptions import MutationAmbiguousError, ValidationError
from ..core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    succeeded_item,
    verification_object,
)
from ..core.operations import (
    Effect,
    Operation,
    operation_effects,
    require_mutation_authorization,
    resolve_invocation,
    run_mutation_async_call,
    run_mutation_call,
    run_read_call,
)
from ..output import OutputFormat, emit_mutation_outcome, output, validate_mutation_output
from ..output.progress import spinner
from ..transformers.transaction_aggregates import (
    transform_recurring_transactions,
    transform_transaction_summary,
)
from ..transformers.transactions import transform_transaction_detail, transform_transactions
from . import transaction_attachments, transaction_splits, transaction_tags

app = typer.Typer(
    help="Transaction management",
    no_args_is_help=True,
)
app.add_typer(transaction_splits.app, name="splits")
app.add_typer(transaction_tags.app, name="tags")
app.add_typer(transaction_attachments.app, name="attachments")

#: Declared effect sets for this group's commands.
LIST_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
GET_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})

#: Concise ordered field selection for ``transactions list`` concise formats
#: (plain/table/compact). Machine-readable formats (JSON, CSV, and NDJSON)
#: always emit the complete normalized transaction fields, and ``--raw`` is
#: untouched. The owner identifier and override timestamp are omitted here
#: because only a legible owner name is useful in a table; both remain
#: available in the machine-readable formats.
TRANSACTION_LIST_DISPLAY_FIELDS: tuple[str, ...] = (
    "id",
    "date",
    "amount",
    "description",
    "category",
    "category_id",
    "account",
    "account_id",
    "is_pending",
    "needs_review",
    "review_status",
    "owner_name",
    "notes",
)
SUMMARY_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
RECURRING_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})

#: Maximum page size accepted by ``transactions list``. The upstream client
#: does not document a server-side cap, so the CLI enforces a bounded,
#: documented limit to prevent unbounded fetch requests.
MAX_PAGE_SIZE = 1000


class TransactionVisibility(StrEnum):
    """Visibility scopes supported by the released upstream list filter."""

    HIDDEN_TRANSACTIONS_ONLY = "hidden_transactions_only"
    ALL_TRANSACTIONS = "all_transactions"


UPDATE_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})
BATCH_UPDATE_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})

MAX_BATCH_CONCURRENCY = 16
MIN_BATCH_CONCURRENCY = 1


@app.command("list")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def list_cmd(
    limit: Annotated[
        int,
        typer.Option(
            "-l",
            "--limit",
            help=(
                "Maximum number of transactions to return (API default: 100; "
                f"maximum page size: {MAX_PAGE_SIZE})"
            ),
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
            help="Filter by tag ID (repeatable)",
        ),
    ] = None,
    has_attachments: Annotated[
        bool | None,
        typer.Option(
            "--has-attachments/--no-has-attachments",
            help="Filter by attachment presence (default: no filter)",
        ),
    ] = None,
    has_notes: Annotated[
        bool | None,
        typer.Option(
            "--has-notes/--no-has-notes",
            help="Filter by note presence (default: no filter)",
        ),
    ] = None,
    hidden_from_reports: Annotated[
        bool | None,
        typer.Option(
            "--hidden-from-reports/--no-hidden-from-reports",
            help="Filter by report visibility (default: no filter)",
        ),
    ] = None,
    is_split: Annotated[
        bool | None,
        typer.Option(
            "--split/--no-split",
            help="Filter by split state (default: no filter)",
        ),
    ] = None,
    is_recurring: Annotated[
        bool | None,
        typer.Option(
            "--recurring/--no-recurring",
            help="Filter by recurring state (default: no filter)",
        ),
    ] = None,
    is_pending: Annotated[
        bool | None,
        typer.Option(
            "--pending/--no-pending",
            help="Filter by pending state (default: no filter)",
        ),
    ] = None,
    imported_from_mint: Annotated[
        bool | None,
        typer.Option(
            "--imported-from-mint/--no-imported-from-mint",
            help="Filter by Mint import origin (default: no filter)",
        ),
    ] = None,
    synced_from_institution: Annotated[
        bool | None,
        typer.Option(
            "--synced-from-institution/--no-synced-from-institution",
            help="Filter by institution sync origin (default: no filter)",
        ),
    ] = None,
    needs_review: Annotated[
        bool | None,
        typer.Option(
            "--needs-review/--no-needs-review",
            help="Filter by review-queue state (default: no filter)",
        ),
    ] = None,
    visibility: Annotated[
        TransactionVisibility | None,
        typer.Option(
            "--visibility",
            help=(
                "Transaction visibility scope (default: non-hidden only; "
                "hidden_transactions_only or all_transactions)"
            ),
        ),
    ] = None,
    search: Annotated[
        str | None,
        typer.Option(
            "--search",
            help="Search term for transaction description/merchant",
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
    via explicit dates or presets, account/category/tag ID filtering,
    tri-state boolean filters (omitted means no filter), visibility scope,
    and text search.

    Examples:
        monarch transactions list                      # Recent transactions
        monarch transactions list --limit 20           # Last 20 transactions
        monarch transactions list --preset this-month  # This month's transactions
        monarch transactions list -s 2024-01-01 -e 2024-01-31  # Date range
        monarch transactions list --account ACC123     # Specific account
        monarch transactions list --search "coffee"    # Search by text
        monarch transactions list --pending            # Only pending transactions
        monarch transactions list --no-pending         # Exclude pending transactions
        monarch transactions list --needs-review       # Review queue
        monarch transactions list --has-attachments    # With attachments
        monarch transactions list -c CAT1 -c CAT2 -t TAG1  # Repeatable filters
        monarch transactions list | jq .              # Auto-JSON when piped
    """
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON
    if ndjson:
        output_format = OutputFormat.COMPACT  # Will handle NDJSON below

    # Parse date range (preset + explicit dates) with the shared strict
    # YYYY-MM-DD validator; invalid dates are structured usage errors.
    start_date = parse_iso_date(start, field="start")
    end_date = parse_iso_date(end, field="end")
    start_str, end_str = parse_date_range(preset, start_date, end_date)

    # Validate everything that can be validated locally BEFORE client
    # creation or any API call: bad input is a structured usage error, never
    # a wasted authenticated request.
    _validate_list_query(
        limit=limit,
        offset=offset,
        start_str=start_str,
        end_str=end_str,
    )

    # Prepare ID filters
    account_ids = list(account) if account else []
    category_ids = list(category) if category else []
    tag_ids = list(tag) if tag else []

    api_kwargs: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "start_date": start_str,
        "end_date": end_str,
        "search": search or "",
        "account_ids": account_ids,
    }
    # Omitted tri-state filters are omitted from the API call entirely so
    # upstream filtering is untouched; present forms map to True/False.
    if category_ids:
        api_kwargs["category_ids"] = category_ids
    if tag_ids:
        api_kwargs["tag_ids"] = tag_ids
    if has_attachments is not None:
        api_kwargs["has_attachments"] = has_attachments
    if has_notes is not None:
        api_kwargs["has_notes"] = has_notes
    if hidden_from_reports is not None:
        api_kwargs["hidden_from_reports"] = hidden_from_reports
    if is_split is not None:
        api_kwargs["is_split"] = is_split
    if is_recurring is not None:
        api_kwargs["is_recurring"] = is_recurring
    if is_pending is not None:
        api_kwargs["is_pending"] = is_pending
    if imported_from_mint is not None:
        api_kwargs["imported_from_mint"] = imported_from_mint
    if synced_from_institution is not None:
        api_kwargs["synced_from_institution"] = synced_from_institution
    if needs_review is not None:
        api_kwargs["needs_review"] = needs_review
    if visibility is not None:
        api_kwargs["transaction_visibility"] = visibility.value

    with spinner("Fetching transactions..."):
        client = get_authenticated_client()
        raw_data: Any = run_read_call(
            lambda: client.get_transactions(**api_kwargs),
            Operation(command="transactions list", effects=LIST_EFFECTS),
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

    output(
        data,
        output_format,
        raw=False,
        display_fields=TRANSACTION_LIST_DISPLAY_FIELDS if not raw else None,
    )


def _validate_list_query(
    limit: int,
    offset: int,
    start_str: str | None,
    end_str: str | None,
) -> None:
    """Validate list query parameters before any client creation or API call.

    Raises:
        ValidationError: On a nonpositive or over-cap limit, a negative
            offset, a one-sided date range, or an inverted date range.
    """
    if limit < 1:
        raise ValidationError(
            message=f"--limit must be a positive integer (got {limit}).",
            field="limit",
        )
    if limit > MAX_PAGE_SIZE:
        raise ValidationError(
            message=(
                f"--limit must not exceed the maximum page size of {MAX_PAGE_SIZE} (got {limit})."
            ),
            field="limit",
        )
    if offset < 0:
        raise ValidationError(
            message=f"--offset must be a nonnegative integer (got {offset}).",
            field="offset",
        )
    if (start_str is None) != (end_str is None):
        raise ValidationError(
            message="--start and --end must be provided together (one-sided "
            "date ranges are not supported).",
            field="dates",
        )
    if start_str is not None and end_str is not None and start_str > end_str:
        raise ValidationError(
            message=f"--start ({start_str}) must be on or before --end ({end_str}).",
            field="dates",
        )


def _resolve_recurring_date_range(
    preset: DatePreset | None,
    start: str | None,
    end: str | None,
) -> tuple[str | None, str | None]:
    """Resolve recurring dates using the released two-sided API contract."""
    if (start is None) != (end is None):
        raise ValidationError(
            message="--start and --end must be provided together.",
            field="start" if start is not None else "end",
        )
    start_date = parse_iso_date(start, field="start")
    end_date = parse_iso_date(end, field="end")
    validate_date_ordering(start_date, end_date)
    return parse_date_range(preset, start_date, end_date)


@app.command("summary")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def summary(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON (shortcut for --format json)"),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option("--raw", help="Output the all-time upstream response without normalization"),
    ] = False,
) -> None:
    """Show the all-time transaction aggregate.

    The released upstream method accepts no date or transaction-list filters;
    this command intentionally exposes none. Use ``cashflow summary`` for a
    date-scoped income/expense report.
    """
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Calculating transaction summary..."):
        client = get_authenticated_client()
        raw_data: Any = run_read_call(
            lambda: client.get_transactions_summary(),
            Operation(command="transactions summary", effects=SUMMARY_EFFECTS),
        )
    output(raw_data if raw else transform_transaction_summary(raw_data), output_format)


@app.command("recurring")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def recurring(
    start: Annotated[
        str | None,
        typer.Option("-s", "--start", help="Start date (YYYY-MM-DD; requires --end)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("-e", "--end", help="End date (YYYY-MM-DD; requires --start)"),
    ] = None,
    preset: Annotated[
        DatePreset | None,
        typer.Option("-p", "--preset", help="Date range preset (for example, this-month or ytd)"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON (shortcut for --format json)"),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option("--raw", help="Output the upstream response without normalization"),
    ] = False,
) -> None:
    """Show recurring activity for the current month or a complete date range.

    With no dates, the released client requests its current-month default.
    Explicit dates must be supplied as a two-sided inclusive range; presets
    use the same shared date semantics as other reporting commands.
    """
    output_format = OutputFormat.JSON if json_output else format
    start_str, end_str = _resolve_recurring_date_range(preset, start, end)
    with spinner("Fetching recurring transactions..."):
        client = get_authenticated_client()
        raw_data: Any = run_read_call(
            lambda: client.get_recurring_transactions(
                start_date=start_str,
                end_date=end_str,
            ),
            Operation(command="transactions recurring", effects=RECURRING_EFFECTS),
        )
    output(raw_data if raw else transform_recurring_transactions(raw_data), output_format)


@app.command("get")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def get_cmd(
    transaction_id: Annotated[
        str,
        typer.Argument(help="Transaction ID to inspect"),
    ],
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help=(
                "Do not redirect a pending transaction ID to its posted "
                "replacement (upstream redirects by default)"
            ),
        ),
    ] = False,
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
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Output raw API response without transformation",
        ),
    ] = False,
) -> None:
    """Get a single transaction's normalized read-only detail.

    Shows the full normalized detail for one transaction, including pending
    and review state, attachments, tags, and split summary. By default the
    upstream service may redirect a pending transaction ID to its posted
    replacement; the requested ID, returned ID, and any original transaction
    identity are always visible in the output so a redirect is never silent.
    Use --strict to request the exact identifier without redirection.

    Examples:
        monarch transactions get TXN123
        monarch transactions get TXN123 --json
        monarch transactions get TXN123 --strict   # No posted redirect
        monarch transactions get TXN123 --raw      # Untouched upstream envelope
    """
    # Validate locally before any client creation or API call.
    if not transaction_id.strip():
        raise ValidationError(
            message="Transaction ID must not be empty.",
            field="transaction_id",
        )

    output_format = OutputFormat.JSON if json_output else format

    with spinner("Fetching transaction..."):
        client = get_authenticated_client()
        raw_data: Any = run_read_call(
            lambda: client.get_transaction_details(
                transaction_id=transaction_id,
                redirect_posted=not strict,
            ),
            Operation(command="transactions get", effects=GET_EFFECTS),
        )

        # Transform unless raw mode
        data = (
            raw_data if raw else transform_transaction_detail(raw_data, requested_id=transaction_id)
        )

    output(data, output_format, raw=False)


UPDATE_VERIFICATION_COMMAND: list[str] = ["monarch", "transactions", "list"]
UPDATE_VERIFICATION_MESSAGE = (
    "Fetch the transaction (e.g. 'monarch transactions list --search' "
    "or the Monarch web UI) and confirm whether the update was "
    "applied before retrying."
)
BATCH_VERIFICATION_MESSAGE = (
    "Verify each affected transaction (e.g. 'monarch transactions list --search' "
    "or the Monarch web UI) and confirm whether each update was applied "
    "before retrying any item."
)


def _finish_mutation(outcome: dict[str, Any]) -> None:
    """Emit a mutation outcome envelope and exit with its status code."""
    emit_mutation_outcome(outcome)


def _reject_positional_targets(legacy: list[str] | None) -> None:
    """Reject a removed positional transaction ID with an actionable error.

    The removed positional form is never silently accepted or reinterpreted;
    callers are pointed at the replacement option instead.
    """
    if legacy:
        raise ValidationError(
            "Positional transaction IDs are no longer supported; use --transaction-id.",
            field="transaction_id",
            details={"removed_positional": True, "replacement_option": "--transaction-id"},
        )


def _validate_transaction_id(transaction_id: str) -> None:
    if not transaction_id.strip():
        raise ValidationError("Transaction ID must not be empty.", field="transaction_id")


def _dedupe_ids(ids: list[str]) -> list[str]:
    """Deduplicate IDs in first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


@app.command(context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def update(
    ctx: typer.Context,
    transaction_id: Annotated[
        str,
        typer.Option("--transaction-id", help="Transaction ID to update"),
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

    This remote mutation requires the global --allow-mutations option, placed
    before the command path (for example:
    monarch --allow-mutations transactions update --transaction-id TXN123 ...).
    Use --dry-run to preview the change without applying it.

    Examples:
        monarch transactions update --transaction-id TXN123 --amount 25.50
        monarch transactions update --transaction-id TXN123 --description "Coffee Shop"
        monarch transactions update --transaction-id TXN123 --category CAT456
        monarch transactions update --transaction-id TXN123 --notes "Business lunch"
        monarch transactions update --transaction-id TXN123 --dry-run --amount 30.00
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)

    # Collect changes
    changes: dict[str, Any] = {}

    if amount is not None:
        # Finite numbers only: NaN/infinity would corrupt state and could emit
        # invalid JSON in a dry-run preview.
        if not math.isfinite(amount):
            raise ValidationError(
                "Amount must be a finite number.",
                field="amount",
                details={"received": str(amount)},
            )
        changes["amount"] = amount
    if description is not None:
        changes["merchant_name"] = description
    if category is not None:
        changes["category_id"] = category
    if notes is not None:
        changes["notes"] = notes
    if date_value is not None:
        parsed_date = parse_iso_date(date_value, field="date")
        assert parsed_date is not None
        changes["date"] = parsed_date.isoformat()

    # Require at least one change. This is a pre-execution input-validation
    # failure: it uses the structured error contract, never a mutation
    # outcome envelope.
    if not changes:
        raise ValidationError(
            message="No changes specified. "
            "Use --amount, --description, --category, --notes, or --date.",
            details={"transaction_id": transaction_id},
        )

    # Classify this parsed invocation. A confirmed --dry-run is a validated
    # preview: no state change, no client creation, and no authorization
    # required. The mutation path retains its declared effects.
    operation = resolve_invocation("transactions update", UPDATE_EFFECTS, dry_run=dry_run)

    # Dry run mode
    if dry_run:
        output(
            {
                "status": "dry_run",
                "transaction_id": transaction_id,
                "changes": changes,
                "message": "No changes applied (dry run mode)",
            }
        )
        return

    # Validate output selection before authorization, which itself precedes
    # authentication lookup, client creation, or any prompt.
    validate_mutation_output()
    require_mutation_authorization(operation)

    # Client creation happens before the mutation attempt: a pre-execution
    # authentication failure must stay on the structured error path, never be
    # misreported as a mutation outcome.
    client = get_authenticated_client()

    # Apply the update. Exactly one attempt: a timeout, disconnect, or
    # cancellation after the request was invoked is reported as an ambiguous
    # mutation-outcome.v1 envelope (exit 4) — remote state may have changed —
    # never as an ordinary failure, and never retried automatically.
    # Definite application rejections produce a failed envelope on the normal
    # operation/API nonzero exit.
    with spinner("Updating transaction..."):
        try:
            run_mutation_call(
                lambda: client.update_transaction(transaction_id=transaction_id, **changes),
                operation,
                entity_ids=(transaction_id,),
                verification=UPDATE_VERIFICATION_MESSAGE,
            )
        except MutationAmbiguousError as e:
            outcome = build_mutation_outcome(
                operation.command,
                [
                    ambiguous_item(
                        "transaction",
                        transaction_id,
                        message=e.message,
                        details={
                            "reason": e.details.get("reason"),
                            "remote_state": "unknown",
                        },
                    )
                ],
                verification=verification_object(
                    e.details.get("verification", UPDATE_VERIFICATION_MESSAGE),
                    command=UPDATE_VERIFICATION_COMMAND,
                ),
            )
            _finish_mutation(outcome)
            return
        except Exception as e:  # noqa: BLE001 - classified by the contract
            # Definitive failure after the request was attempted: the update
            # did not succeed and the rejection is not ambiguous. The error
            # object is sanitized by the shared contract helper.
            error = error_from_exception(e)
            _finish_mutation(
                build_mutation_outcome(
                    operation.command,
                    [
                        failed_item(
                            "transaction",
                            transaction_id,
                            code=error["code"],
                            message=error["message"],
                            details=error["details"],
                        )
                    ],
                )
            )
            return

    _finish_mutation(
        build_mutation_outcome(
            operation.command,
            [succeeded_item("transaction", transaction_id, {"changes": changes})],
        )
    )


@app.command("batch-update", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def batch_update(
    ctx: typer.Context,
    transaction_id: Annotated[
        list[str] | None,
        typer.Option("--transaction-id", help="Transaction ID to update (repeatable)"),
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
            help="Maximum parallel API calls (1-16; local safety cap)",
        ),
    ] = 4,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview changes without applying them",
        ),
    ] = False,
) -> None:
    """Batch update multiple transactions at once.

    Apply the same changes to multiple transactions efficiently using
    parallel API calls. Transaction IDs can be passed with repeatable
    --transaction-id options, piped via stdin, or both. Repeatable option
    values are consumed first, then stdin lines; the combined list is
    deduplicated in first-seen order before any update is attempted.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path (for example:
    monarch --allow-mutations transactions batch-update ...). Use --dry-run to
    preview the changes without applying them; --dry-run --yes is accepted and
    irrelevant.

    Examples:
        # Update specific transactions
        monarch transactions batch-update --transaction-id TXN001 --transaction-id TXN002 \\
            --category CAT123

        # Pipe IDs from a search
        monarch transactions list --search "Coffee" --quiet | \\
            monarch transactions batch-update --stdin --category CAT456

        # Preview changes first
        monarch transactions batch-update --transaction-id TXN001 --category CAT123 --dry-run

        # Set notes on multiple transactions
        monarch transactions batch-update --stdin --notes "Q1 Expenses" < ids.txt
    """
    _reject_positional_targets(ctx.args)
    if max_concurrency < MIN_BATCH_CONCURRENCY or max_concurrency > MAX_BATCH_CONCURRENCY:
        raise ValidationError(
            f"--max-concurrency must be an integer between {MIN_BATCH_CONCURRENCY} "
            f"and {MAX_BATCH_CONCURRENCY} (a local safety cap).",
            field="max_concurrency",
            details={"min": MIN_BATCH_CONCURRENCY, "max": MAX_BATCH_CONCURRENCY},
        )
    operation = resolve_invocation(
        "transactions batch-update", BATCH_UPDATE_EFFECTS, dry_run=dry_run
    )

    # Authorize before reading stdin, authentication lookup, client creation,
    # or any prompt. Dry-run invocations are classified as previews and skip
    # this gate below.
    validate_mutation_output()
    if not dry_run:
        require_mutation_authorization(operation)

    # Collect transaction IDs: repeatable option values first, then stdin.
    ids: list[str] = []

    if transaction_id:
        ids.extend(item.strip() for item in transaction_id)

    if stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:  # Skip empty lines
                ids.append(line)

    # Validate we have IDs to process. Pre-execution input-validation
    # failures use the structured error contract, never a mutation outcome.
    if not ids:
        raise ValidationError(
            message="No transaction IDs provided. Pass --transaction-id or use --stdin.",
            field="transaction_id",
        )
    empty = [item for item in ids if not item]
    if empty:
        raise ValidationError(
            message="Transaction IDs must not be empty.",
            field="transaction_id",
            details={"empty_count": len(empty)},
        )

    # Deduplicate in first-seen order so a transaction is never updated twice.
    ids = _dedupe_ids(ids)

    # Validate we have at least one change
    changes: dict[str, Any] = {}
    if category is not None:
        changes["category_id"] = category
    if notes is not None:
        changes["notes"] = notes

    if not changes:
        raise ValidationError(
            message="No changes specified. Use --category/-c or --notes/-n.",
        )

    # Dry run mode - just show what would happen
    if dry_run:
        output(
            {
                "status": "dry_run",
                "transaction_count": len(ids),
                "transaction_ids": ids,
                "changes": changes,
                "message": f"Would update {len(ids)} transaction(s) (dry run mode)",
            }
        )
        return

    # Execute batch update. Each item runs through the single-attempt
    # mutation executor: transport uncertainty (timeout/disconnect/cancel
    # after dispatch) is an ambiguous item — the update may have been applied
    # — while definite application rejections remain failed items. Input
    # order is preserved in the per-item outcomes.
    async def do_batch_update() -> list[dict[str, Any]]:
        """Execute parallel batch updates with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def update_one(txn_id: str) -> dict[str, Any]:
            """Update a single transaction with bounded concurrency.

            The shared mutation executor applies the per-attempt timeout and
            converts ambiguous transport failures into
            MutationAmbiguousError; this wrapper only classifies the outcome.
            """
            async with semaphore:
                try:
                    await run_mutation_async_call(
                        lambda: get_authenticated_client().update_transaction(
                            transaction_id=txn_id, **changes
                        ),
                        operation,
                        entity_ids=(txn_id,),
                        verification=BATCH_VERIFICATION_MESSAGE,
                    )
                    return succeeded_item("transaction", txn_id, {"changes": changes})
                except MutationAmbiguousError as e:
                    return ambiguous_item(
                        "transaction",
                        txn_id,
                        message=e.message,
                        details={
                            "reason": e.details.get("reason"),
                            "remote_state": "unknown",
                        },
                    )
                except Exception as e:
                    error = error_from_exception(e)
                    return failed_item(
                        "transaction",
                        txn_id,
                        code=error["code"],
                        message=error["message"],
                        details=error["details"],
                    )

        # Run all updates concurrently; asyncio.gather preserves input order.
        return list(await asyncio.gather(*(update_one(txn_id) for txn_id in ids)))

    with spinner(f"Updating {len(ids)} transaction(s)..."):
        try:
            items = run_async(do_batch_update())
        except KeyboardInterrupt:
            # The interrupt cancelled the batch task before the completed
            # per-item records could be collected. Some or all requests may
            # have been dispatched, so every requested transaction is
            # reported as an ambiguous item (exit 4) with a required
            # verification object instead of a silent "Interrupted." exit
            # 130 with no verification guidance.
            _finish_mutation(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            txn_id,
                            message=(
                                "The batch update was interrupted after requests "
                                "may have been dispatched; remote state may have "
                                "changed. Do not retry before verifying."
                            ),
                            details={"reason": "cancelled", "remote_state": "unknown"},
                        )
                        for txn_id in ids
                    ],
                    verification=verification_object(
                        BATCH_VERIFICATION_MESSAGE,
                        command=UPDATE_VERIFICATION_COMMAND,
                    ),
                )
            )
            return

    _finish_mutation(
        build_mutation_outcome(
            operation.command,
            items,
            verification=verification_object(
                BATCH_VERIFICATION_MESSAGE,
                command=UPDATE_VERIFICATION_COMMAND,
            ),
        )
    )
