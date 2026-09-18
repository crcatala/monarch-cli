"""Transaction commands for Monarch CLI."""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from enum import StrEnum
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range
from ..core.error_handler import handle_errors
from ..core.exceptions import MutationAmbiguousError, ValidationError
from ..core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    outcome_exit_code,
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
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.transactions import transform_transaction_detail, transform_transactions

app = typer.Typer(
    help="Transaction management",
    no_args_is_help=True,
)

#: Declared effect sets for this group's commands.
LIST_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
GET_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})

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

    # Parse date range (preset + explicit dates)
    start_date = _parse_date(start)
    end_date = _parse_date(end)
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

    output(data, output_format, raw=False)


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
    output(outcome)
    code = outcome_exit_code(outcome["status"])
    if code:
        raise typer.Exit(code)


@app.command()
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
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

    # Authorize before authentication lookup, client creation, or any prompt.
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


@app.command("batch-update")
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
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
    # Classify this parsed invocation before any prompt or client creation.
    operation = resolve_invocation(
        "transactions batch-update", BATCH_UPDATE_EFFECTS, dry_run=dry_run
    )

    # Authorize before reading stdin, authentication lookup, client creation,
    # or any prompt. Dry-run invocations are classified as previews and skip
    # this gate below.
    if not dry_run:
        require_mutation_authorization(operation)

    # Collect transaction IDs
    ids: list[str] = []

    if transaction_ids:
        ids.extend(transaction_ids)

    if stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:  # Skip empty lines
                ids.append(line)

    # Validate we have IDs to process. Pre-execution input-validation
    # failures use the structured error contract, never a mutation outcome.
    if not ids:
        raise ValidationError(
            message="No transaction IDs provided. Pass IDs as arguments or use --stdin.",
        )

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
