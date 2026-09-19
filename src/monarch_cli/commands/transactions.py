"""Transaction commands for Monarch CLI."""

from __future__ import annotations

import asyncio
import math
import sys
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range, parse_iso_date, validate_date_ordering
from ..core.error_handler import handle_errors
from ..core.exceptions import (
    APIError,
    MutationAmbiguousError,
    NotFoundError,
    ValidationError,
)
from ..core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    outcome_operation,
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
from . import transaction_attachments, transaction_review, transaction_splits, transaction_tags
from .mutation_helpers import (
    as_object as _as_object,
)
from .mutation_helpers import (
    confirm_destructive,
)
from .mutation_helpers import (
    payload_error_details as _payload_error_details,
)

app = typer.Typer(
    help="Transaction management",
    no_args_is_help=True,
)
app.add_typer(transaction_splits.app, name="splits")
app.add_typer(transaction_tags.app, name="tags")
app.add_typer(transaction_attachments.app, name="attachments")
app.add_typer(transaction_review.app, name="review")

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


# --- Manual transaction create/delete (mc-yqfi) -----------------------------
#
# A minimal, explicit lifecycle for one manual transaction. Create uses the
# released public ``create_transaction`` capability and performs a bounded
# exact-ID readback; delete is single-target only and verifies absence when
# the released read capability supports it. Neither command claims
# idempotency or recoverability: an uncertain create/delete is reported as
# ambiguous with safe verification guidance, never retried blindly.

CREATE_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})
DELETE_EFFECTS: frozenset[Effect] = frozenset({Effect.REMOTE_MUTATION})

#: Tokenized safe verification commands for the create/delete lifecycle.
CREATE_VERIFICATION_COMMAND: list[str] = ["monarch", "transactions", "list"]
DELETE_VERIFICATION_COMMAND: list[str] = ["monarch", "transactions", "get"]
CREATE_VERIFICATION_MESSAGE = (
    "A create can succeed even when its response is lost. Do not retry "
    "blindly: verify whether the transaction now exists (for example "
    "'monarch transactions list --search MERCHANT' or the Monarch web UI) "
    "before creating it again."
)
DELETE_VERIFICATION_MESSAGE = (
    "Verify whether the transaction still exists with 'monarch transactions "
    "get TRANSACTION_ID' (a not-found result confirms deletion) before "
    "retrying."
)


def _validate_required_id(value: str, option: str) -> None:
    """Reject an empty (or whitespace-only) required opaque ID."""
    if not value.strip():
        raise ValidationError(f"--{option} must be a non-empty ID.", field=option.replace("-", "_"))


def _fetch_exact_detail(client: Any, transaction_id: str, command: str) -> Mapping[str, Any] | None:
    """Read one transaction detail without a pending-ID redirect.

    Returns the exact detail object, or ``None`` when the service reports no
    such transaction. The read is observational: it happens through the read
    executor, never the mutation executor.
    """
    payload = run_read_call(
        lambda: client.get_transaction_details(
            transaction_id=transaction_id, redirect_posted=False
        ),
        Operation(command=command, effects=GET_EFFECTS),
    )
    response = _as_object(payload, "transaction detail")
    detail = response.get("getTransaction")
    if detail is None:
        return None
    return _as_object(detail, "transaction detail")


def _created_transaction_id(payload: Any) -> str:
    """Extract the created transaction ID from a create response.

    A definite payload rejection raises :class:`APIError` (a definitive
    failure). A response whose outcome cannot be resolved to an identity
    raises :class:`MutationAmbiguousError`: the request was already
    dispatched and may have created the transaction, so a missing ID or a
    malformed response is never reported as an ordinary failure.
    """
    if not isinstance(payload, Mapping):
        raise MutationAmbiguousError(
            "The create returned a malformed response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "createTransaction"},
        )
    if payload.get("errors"):
        raise APIError(
            message="The transaction create was rejected by the service.",
            details={"payload_errors": _payload_error_details(payload["errors"])},
        )
    container = payload.get("createTransaction")
    if not isinstance(container, Mapping):
        raise MutationAmbiguousError(
            "The create returned an incomplete response; remote state is unknown.",
            details={"reason": "malformed_response", "field": "createTransaction"},
        )
    errors = container.get("errors")
    if errors:
        raise APIError(
            message="The transaction create was rejected by the service.",
            details={"payload_errors": _payload_error_details(errors)},
        )
    transaction = container.get("transaction")
    transaction_id = transaction.get("id") if isinstance(transaction, Mapping) else None
    if not isinstance(transaction_id, str) or not transaction_id.strip():
        raise MutationAmbiguousError(
            "The create response did not include a transaction ID; the "
            "transaction may still have been created.",
            details={
                "reason": "missing_identity",
                "field": "createTransaction.transaction.id",
            },
        )
    return transaction_id


def _mapping_id(value: Any) -> str | None:
    return value.get("id") if isinstance(value, Mapping) else None


def _merchant_name(value: Any) -> str | None:
    return value.get("name") if isinstance(value, Mapping) else None


def _created_result(transaction_id: str, detail: Mapping[str, Any]) -> dict[str, Any]:
    """Normalized observed identity/fields for a verified create."""
    return {
        "transaction_id": transaction_id,
        "date": detail.get("date"),
        "amount": detail.get("amount"),
        "account_id": _mapping_id(detail.get("account")),
        "category_id": _mapping_id(detail.get("category")),
        "merchant": _merchant_name(detail.get("merchant")),
        "notes": detail.get("notes"),
    }


def _create_mismatch(
    detail: Mapping[str, Any], normalized: dict[str, Any]
) -> dict[str, Any] | None:
    """Compare a readback detail against the requested create input.

    Only fields the released detail response exposes are compared. A
    requested empty note is satisfied by an absent or empty observed note.
    """
    mismatched: list[str] = []
    if detail.get("date") != normalized["date"]:
        mismatched.append("date")
    observed_amount = detail.get("amount")
    amount_matches = False
    if isinstance(observed_amount, (int, float)) and not isinstance(observed_amount, bool):
        amount_matches = round(float(observed_amount), 2) == round(float(normalized["amount"]), 2)
    if not amount_matches:
        mismatched.append("amount")
    if _mapping_id(detail.get("account")) != normalized["account_id"]:
        mismatched.append("account_id")
    if _mapping_id(detail.get("category")) != normalized["category_id"]:
        mismatched.append("category_id")
    if _merchant_name(detail.get("merchant")) != normalized["merchant"]:
        mismatched.append("merchant")
    observed_notes = detail.get("notes")
    if normalized["notes"]:
        if observed_notes != normalized["notes"]:
            mismatched.append("notes")
    elif observed_notes not in (None, ""):
        mismatched.append("notes")
    if not mismatched:
        return None
    return {
        "mismatched_fields": mismatched,
        "observed": _created_result(normalized.get("transaction_id", "unknown"), detail),
    }


@app.command("create", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def create_transaction(
    ctx: typer.Context,
    date_value: Annotated[str, typer.Option("--date", help="Transaction date (YYYY-MM-DD)")],
    account_id: Annotated[str, typer.Option("--account-id", help="Account ID")],
    amount: Annotated[float, typer.Option("--amount", help="Transaction amount")],
    merchant: Annotated[str, typer.Option("--merchant", help="Merchant/description name")],
    category_id: Annotated[str, typer.Option("--category-id", help="Category ID")],
    notes: Annotated[str, typer.Option("--notes", help="Optional transaction notes")] = "",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate the input without creating anything"),
    ] = False,
) -> None:
    """Create one manual transaction.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. Required: --date, --account-id, --amount,
    --merchant, and --category-id; --notes is optional. This version does not
    expose tags, dedupe/upsert, duplicate detection, batch operations,
    --update-balance, attachments, or account/category management. Create is
    not idempotent: if the response is lost, verify before retrying. Use
    --dry-run to validate the input without authenticating or writing.

    Examples:
        monarch --allow-mutations transactions create \\
            --date 2026-01-15 --account-id ACC1 --amount 12.34 \\
            --merchant "Coffee Shop" --category-id CAT1
        monarch transactions create --date 2026-01-15 --account-id ACC1 \\
            --amount 12.34 --merchant "Coffee Shop" --category-id CAT1 --dry-run
    """
    _reject_positional_targets(ctx.args)
    parsed_date = parse_iso_date(date_value, field="date")
    assert parsed_date is not None
    _validate_required_id(account_id, "account-id")
    _validate_required_id(category_id, "category-id")
    if not math.isfinite(amount):
        raise ValidationError(
            "Amount must be a finite number.",
            field="amount",
            details={"received": str(amount)},
        )
    merchant_name = merchant.strip()
    if not merchant_name:
        raise ValidationError("Merchant must be non-empty after trimming.", field="merchant")

    normalized: dict[str, Any] = {
        "date": parsed_date.isoformat(),
        "account_id": account_id,
        "amount": amount,
        "merchant": merchant_name,
        "category_id": category_id,
        "notes": notes,
    }

    operation = resolve_invocation("transactions create", CREATE_EFFECTS, dry_run=dry_run)
    if dry_run:
        emit_mutation_outcome(
            {
                "status": "dry_run",
                "operation": outcome_operation("transactions create"),
                "target": {"account_id": account_id, "date": normalized["date"]},
                "detail": {
                    "amount": amount,
                    "merchant": merchant_name,
                    "category_id": category_id,
                    "notes": notes,
                },
            }
        )
        return

    validate_mutation_output()
    require_mutation_authorization(operation)
    client = get_authenticated_client()

    with spinner("Creating transaction..."):
        try:
            payload = run_mutation_call(
                lambda: client.create_transaction(
                    date=normalized["date"],
                    account_id=account_id,
                    amount=amount,
                    merchant_name=merchant_name,
                    category_id=category_id,
                    notes=notes,
                ),
                operation,
                verification=CREATE_VERIFICATION_MESSAGE,
            )
            transaction_id = _created_transaction_id(payload)
        except typer.Exit:
            raise
        except MutationAmbiguousError as exc:
            _finish_mutation(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            "unknown",
                            exc.message,
                            {
                                "remote_state": "unknown",
                                "reason": exc.details.get("reason"),
                            },
                        )
                    ],
                    verification=verification_object(
                        CREATE_VERIFICATION_MESSAGE, command=CREATE_VERIFICATION_COMMAND
                    ),
                )
            )
            return
        except Exception as exc:
            error = error_from_exception(exc)
            _finish_mutation(
                build_mutation_outcome(
                    operation.command,
                    [
                        failed_item(
                            "transaction",
                            "unknown",
                            error["code"],
                            error["message"],
                            error["details"],
                        )
                    ],
                )
            )
            return

    # Bounded exact-ID readback. A missing ID, malformed response, timeout,
    # disconnect, or verification mismatch is never reported as success.
    try:
        detail = _fetch_exact_detail(client, transaction_id, "transactions create verify")
    except typer.Exit:
        raise
    except Exception:  # noqa: BLE001 - a dispatched create with no readback is ambiguous
        _emit_create_ambiguous(
            operation.command,
            transaction_id,
            "The transaction was created remotely but could not be verified; "
            "remote state is unknown.",
            {"reason": "verification_unavailable", "remote_state": "unknown"},
        )
        return

    if detail is None or detail.get("id") != transaction_id:
        _emit_create_ambiguous(
            operation.command,
            transaction_id,
            "The created transaction could not be read back by its exact ID; "
            "remote state is unknown.",
            {
                "reason": "verification_mismatch",
                "observed_transaction_id": detail.get("id") if detail is not None else None,
                "remote_state": "unknown",
            },
        )
        return

    normalized["transaction_id"] = transaction_id
    mismatch = _create_mismatch(detail, normalized)
    if mismatch is not None:
        _emit_create_ambiguous(
            operation.command,
            transaction_id,
            "The created transaction could not be verified as requested; remote state is unknown.",
            {"reason": "verification_mismatch", "remote_state": "unknown", **mismatch},
        )
        return

    result = _created_result(transaction_id, detail)
    _finish_mutation(
        build_mutation_outcome(
            operation.command,
            [succeeded_item("transaction", transaction_id, result)],
        )
    )


def _emit_create_ambiguous(
    command: str,
    transaction_id: str,
    message: str,
    details: dict[str, Any],
) -> None:
    _finish_mutation(
        build_mutation_outcome(
            command,
            [ambiguous_item("transaction", transaction_id, message, details)],
            verification=verification_object(
                CREATE_VERIFICATION_MESSAGE,
                command=[*CREATE_VERIFICATION_COMMAND, transaction_id],
            ),
        )
    )


@app.command("delete", context_settings={"allow_extra_args": True})
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def delete_transaction(
    ctx: typer.Context,
    transaction_id: Annotated[
        str,
        typer.Option("--transaction-id", help="Transaction ID to delete"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate the target without deleting anything"),
    ] = False,
) -> None:
    """Delete one manual transaction.

    This remote mutation requires the global --allow-mutations option, placed
    before the command path. The target is a required --transaction-id option
    and is single-target only; bulk IDs are never accepted. Destructive:
    prompts unless --yes is given after --allow-mutations; --yes never
    authorizes the write. Delete is not recoverable, and an uncertain result
    is reported as ambiguous rather than a claimed deletion. Use --dry-run to
    validate the target without authenticating or writing.

    Examples:
        monarch --allow-mutations --yes transactions delete --transaction-id TXN123
        monarch transactions delete --transaction-id TXN123 --dry-run
    """
    _reject_positional_targets(ctx.args)
    _validate_transaction_id(transaction_id)

    operation = resolve_invocation("transactions delete", DELETE_EFFECTS, dry_run=dry_run)
    if dry_run:
        emit_mutation_outcome(
            {
                "status": "dry_run",
                "operation": outcome_operation("transactions delete"),
                "target": {"transaction_id": transaction_id},
                "detail": {"action": "delete", "destructive": True},
            }
        )
        return

    validate_mutation_output()
    require_mutation_authorization(operation)
    client = get_authenticated_client()

    # Read the exact target before deletion so a missing or mismatched target
    # is a deterministic pre-mutation error, never a claimed deletion. A read
    # failure here happens before any mutation was dispatched, so it stays on
    # the structured error path rather than the mutation-outcome contract.
    before = _fetch_exact_detail(client, transaction_id, "transactions delete verify")
    if before is None:
        raise NotFoundError(
            message="Transaction not found.",
            resource_type="transaction",
            resource_id=transaction_id,
        )
    if before.get("id") != transaction_id:
        raise APIError(
            message=(
                "The requested transaction ID did not match the returned "
                "transaction; refusing to delete without exact target identity."
            ),
            details={"reason": "target_identity_mismatch", "requested_id": transaction_id},
        )

    confirm_destructive(
        f"Permanently delete transaction {transaction_id}?", operation=operation.command
    )

    with spinner("Deleting transaction..."):
        try:
            deleted = run_mutation_call(
                lambda: client.delete_transaction(transaction_id),
                operation,
                entity_ids=(transaction_id,),
                verification=DELETE_VERIFICATION_MESSAGE,
            )
        except typer.Exit:
            raise
        except MutationAmbiguousError as exc:
            _finish_mutation(
                build_mutation_outcome(
                    operation.command,
                    [
                        ambiguous_item(
                            "transaction",
                            transaction_id,
                            exc.message,
                            {
                                "remote_state": "unknown",
                                "reason": exc.details.get("reason"),
                            },
                        )
                    ],
                    verification=verification_object(
                        DELETE_VERIFICATION_MESSAGE,
                        command=[*DELETE_VERIFICATION_COMMAND, transaction_id],
                    ),
                )
            )
            return
        except Exception as exc:
            error = error_from_exception(exc)
            _finish_mutation(
                build_mutation_outcome(
                    operation.command,
                    [
                        failed_item(
                            "transaction",
                            transaction_id,
                            error["code"],
                            error["message"],
                            error["details"],
                        )
                    ],
                )
            )
            return

    if not deleted:
        # Defensive: the released client reports a rejected delete by raising,
        # but a falsy result is a definitive non-success, never a deletion.
        _finish_mutation(
            build_mutation_outcome(
                operation.command,
                [
                    failed_item(
                        "transaction",
                        transaction_id,
                        code="API_ERROR",
                        message="The delete request was not accepted by the service.",
                        details={},
                    )
                ],
            )
        )
        return

    # Verify absence where the released read capability supports it. A read
    # that fails, or that still returns the transaction, leaves the outcome
    # unconfirmed and is reported as ambiguous, never as a claimed deletion.
    try:
        after = _fetch_exact_detail(client, transaction_id, "transactions delete verify")
    except typer.Exit:
        raise
    except Exception:  # noqa: BLE001 - an unverified delete is ambiguous
        _finish_mutation(
            build_mutation_outcome(
                operation.command,
                [
                    ambiguous_item(
                        "transaction",
                        transaction_id,
                        "The delete was dispatched but could not be verified; "
                        "remote state is unknown.",
                        {"reason": "verification_unavailable", "remote_state": "unknown"},
                    )
                ],
                verification=verification_object(
                    DELETE_VERIFICATION_MESSAGE,
                    command=[*DELETE_VERIFICATION_COMMAND, transaction_id],
                ),
            )
        )
        return
    if after is not None:
        _finish_mutation(
            build_mutation_outcome(
                operation.command,
                [
                    ambiguous_item(
                        "transaction",
                        transaction_id,
                        "The transaction is still present after the delete request; "
                        "remote state is unknown.",
                        {"reason": "verification_mismatch", "remote_state": "unknown"},
                    )
                ],
                verification=verification_object(
                    DELETE_VERIFICATION_MESSAGE,
                    command=[*DELETE_VERIFICATION_COMMAND, transaction_id],
                ),
            )
        )
        return

    _finish_mutation(
        build_mutation_outcome(
            operation.command,
            [succeeded_item("transaction", transaction_id, {"deleted": True})],
        )
    )
