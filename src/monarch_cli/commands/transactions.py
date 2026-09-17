"""Transaction commands for Monarch CLI."""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range
from ..core.error_handler import handle_errors
from ..core.exceptions import MutationAmbiguousError
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
from ..transformers.transactions import transform_transactions

app = typer.Typer(
    help="Transaction management",
    no_args_is_help=True,
)

#: Declared effect sets for this group's commands.
LIST_EFFECTS: frozenset[Effect] = frozenset({Effect.READ_ONLY})
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

    with spinner("Fetching transactions..."):
        client = get_authenticated_client()
        raw_data: Any = run_read_call(
            lambda: client.get_transactions(
                limit=limit,
                offset=offset,
                start_date=start_str,
                end_date=end_str,
                search=search or "",
                account_ids=account_ids,
            ),
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

    # Require at least one change
    if not changes:
        output(
            {
                "status": "error",
                "transaction_id": transaction_id,
                "message": "No changes specified. "
                "Use --amount, --description, --category, --notes, or --date.",
            }
        )
        raise typer.Exit(1)

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

    # Apply the update. Exactly one attempt: a timeout, disconnect, or
    # cancellation after the request was invoked is reported as
    # MUTATION_AMBIGUOUS (exit 4) — remote state may have changed — never as
    # an ordinary failure, and never retried automatically.
    with spinner("Updating transaction..."):
        run_mutation_call(
            lambda: get_authenticated_client().update_transaction(
                transaction_id=transaction_id, **changes
            ),
            operation,
            entity_ids=(transaction_id,),
            verification=(
                "Fetch the transaction (e.g. 'monarch transactions list --search' "
                "or the Monarch web UI) and confirm whether the update was "
                "applied before retrying."
            ),
        )

    output(
        {
            "status": "updated",
            "transaction_id": transaction_id,
            "changes": changes,
        }
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

    # Validate we have IDs to process
    if not ids:
        output(
            {
                "status": "error",
                "message": "No transaction IDs provided. Pass IDs as arguments or use --stdin.",
            }
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
                "message": "No changes specified. Use --category/-c or --notes/-n.",
            }
        )
        raise typer.Exit(1)

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
    # after dispatch) is labeled "ambiguous" — the item may have been applied
    # — while definite application rejections remain "error". Input order is
    # preserved in the per-item results.
    _BATCH_VERIFICATION = (
        "Fetch the transaction (e.g. 'monarch transactions list --search' or "
        "the Monarch web UI) and confirm whether the update was applied "
        "before retrying this item."
    )

    async def do_batch_update() -> dict[str, Any]:
        """Execute parallel batch updates with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrency)
        results: list[dict[str, Any]] = []

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
                        verification=_BATCH_VERIFICATION,
                    )
                    return {"id": txn_id, "status": "success"}
                except MutationAmbiguousError as e:
                    return {
                        "id": txn_id,
                        "status": "ambiguous",
                        "error_code": e.code.value,
                        "message": e.message,
                        "verification": e.details.get("verification"),
                    }
                except Exception as e:
                    return {"id": txn_id, "status": "error", "error": str(e)}

        # Run all updates concurrently; asyncio.gather preserves input order.
        tasks = [update_one(txn_id) for txn_id in ids]
        results = await asyncio.gather(*tasks)

        # Summarize results
        successes = [r for r in results if r["status"] == "success"]
        ambiguous = [r for r in results if r["status"] == "ambiguous"]
        failures = [r for r in results if r["status"] == "error"]

        return {
            "status": "completed",
            "success_count": len(successes),
            "failure_count": len(failures),
            "ambiguous_count": len(ambiguous),
            # Keep the complete ordered per-item record for automation. The
            # summary lists below remain for compatibility with the original
            # command-specific result shape.
            "results": results,
            "changes": changes,
            "failures": failures if failures else None,
            "ambiguous": ambiguous if ambiguous else None,
        }

    with spinner(f"Updating {len(ids)} transaction(s)..."):
        try:
            result = run_async(do_batch_update())
        except KeyboardInterrupt as e:
            # The interrupt cancelled the batch task before the completed
            # per-item records could be collected. Some or all requests may
            # have been dispatched, so report a batch-level ambiguity
            # covering every requested ID instead of a silent "Interrupted."
            # exit 130 with no verification guidance.
            raise MutationAmbiguousError(
                message=(
                    f"Batch update 'transactions batch-update' was interrupted "
                    "(cancelled after requests may have been dispatched). "
                    f"Remote state may have changed for some or all of "
                    f"{len(ids)} transaction(s); do not retry blindly. Verify "
                    "each requested transaction first: "
                    f"{', '.join(ids)}. " + _BATCH_VERIFICATION
                ),
                details={
                    "operation": "transactions batch-update",
                    "entity_ids": list(ids),
                    "remote_state": "unknown",
                    "reason": "cancelled",
                    "attempts": len(ids),
                    "verification": (
                        "Verify each requested transaction via read commands "
                        "or the Monarch web UI before re-running the batch; " + _BATCH_VERIFICATION
                    ),
                },
            ) from e

    output(result)

    # Any definite failure or ambiguous item makes the invocation fail:
    # ambiguous items may have been applied and must be verified by a human
    # or agent before any retry.
    if result["failure_count"] or result["ambiguous_count"]:
        raise typer.Exit(1)
