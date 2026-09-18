"""Account commands for Monarch CLI."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.error_handler import handle_errors
from ..core.mutation_outcomes import outcome_exit_code
from ..core.operations import (
    Effect,
    Operation,
    operation_effects,
    require_mutation_authorization,
    run_read_call,
)
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.accounts import (
    get_account_history,
    get_account_snapshots_by_type,
    get_account_type_options,
    get_aggregate_snapshots,
    get_recent_account_balances,
    get_refresh_status,
    list_account_types,
    list_accounts,
    refresh_accounts,
)

app = typer.Typer(
    help="Account management",
    no_args_is_help=True,
)


class SnapshotTimeframe(StrEnum):
    """Timeframes supported by type-scoped account snapshots."""

    MONTH = "month"
    YEAR = "year"


@app.command("list")
@handle_errors
@operation_effects(Effect.READ_ONLY)
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
            data: Any = run_read_call(
                lambda: client.get_accounts(),
                Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY})),
            )
        else:
            # Normal mode: use service with transformation
            data = list_accounts(
                Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY}))
            )

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


@app.command("types")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def types_cmd(
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
            help="Output the raw API response without normalization",
        ),
    ] = False,
) -> None:
    """List supported account groups, types, and subtypes.

    Exposes the authoritative account hierarchy accepted by account
    workflows (for example manual-account creation and snapshot filters) so
    callers do not have to guess identifiers.

    Normalized records contain stable ``group`` > ``type`` > ``subtype``
    identifiers plus ``type_display``/``subtype_display`` labels. Ordering
    follows the upstream first-seen type order and, within a type, the
    upstream subtype order. Duplicate identifiers are collapsed. Record
    fields are always present; unavailable values are ``null``.

    This command is read-only and never modifies remote state.

    Examples:
        monarch accounts types                # Plain format (default in terminal)
        monarch accounts types --json         # JSON format
        monarch accounts types --format table # Table format
        monarch accounts types | jq .         # Auto-JSON when piped
        monarch accounts types --raw          # Raw API response
    """
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    operation = Operation(command="accounts types", effects=frozenset({Effect.READ_ONLY}))

    with spinner("Fetching account types..."):
        if raw:
            data: Any = get_account_type_options(operation)
        else:
            data = list_account_types(operation)

    output(data, output_format, raw=False)


@app.command()
@handle_errors
@operation_effects(Effect.READ_ONLY)
def history(
    account_id: Annotated[
        str,
        typer.Argument(
            help="Account ID (opaque string; passed to the API verbatim, never coerced)",
        ),
    ],
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
            help="Output raw API response without normalization",
        ),
    ] = False,
) -> None:
    """Show normalized balance history for one account.

    The account ID is treated as an opaque non-empty string and passed to the
    API verbatim. Hidden, manual, and deactivated accounts remain inspectable
    when identified directly. Missing balances stay null; an empty history is
    an empty list, never an invented value.

    This command is read-only and never modifies remote state.

    Examples:
        monarch accounts history ACC123 --json
        monarch accounts history ACC123 --raw
    """
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching account history..."):
        data: Any = get_account_history(account_id, raw=raw)

    output(data, output_format, raw=False)


@app.command("recent-balances")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def recent_balances(
    start: Annotated[
        str | None,
        typer.Option(
            "-s",
            "--start",
            help="Inclusive start date (YYYY-MM-DD). Omit for the upstream default (last 31 days).",
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
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Output raw API response without normalization",
        ),
    ] = False,
) -> None:
    """Show recent daily balances for all accounts from a start date.

    The released upstream capability accepts a start date only; there is no
    end-date filter, so none is offered here. Invalid dates fail before any
    API call.

    This command is read-only and never modifies remote state.

    Examples:
        monarch accounts recent-balances --json
        monarch accounts recent-balances --start 2024-01-01
    """
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching recent balances..."):
        data: Any = get_recent_account_balances(start, raw=raw)

    output(data, output_format, raw=False)


@app.command("snapshots")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def snapshots(
    start: Annotated[
        str,
        typer.Option(
            "-s",
            "--start",
            help="Inclusive start date (YYYY-MM-DD)",
        ),
    ],
    end: Annotated[
        str,
        typer.Option(
            "-e",
            "--end",
            help="Inclusive end date (YYYY-MM-DD)",
        ),
    ],
    account_type: Annotated[
        str | None,
        typer.Option(
            "-t",
            "--account-type",
            help=(
                "Optional account type filter; must be a type identifier from "
                "'monarch accounts types'"
            ),
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
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Output raw API response without normalization",
        ),
    ] = False,
) -> None:
    """Show aggregate (net-worth) snapshots over a validated date range.

    Both --start and --end are required; the upstream aggregate snapshot
    query does not support one-sided ranges. The optional --account-type
    filter is validated against 'monarch accounts types' before any API call.

    This command is read-only and never modifies remote state.

    Examples:
        monarch accounts snapshots --start 2024-01-01 --end 2024-12-31 --json
        monarch accounts snapshots -s 2024-01-01 -e 2024-06-30 -t asset
    """
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching aggregate snapshots..."):
        data: Any = get_aggregate_snapshots(start, end, account_type=account_type, raw=raw)

    output(data, output_format, raw=False)


@app.command("snapshots-by-type")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def snapshots_by_type(
    start: Annotated[
        str,
        typer.Option(
            "-s",
            "--start",
            help="Inclusive start date (YYYY-MM-DD)",
        ),
    ],
    timeframe: Annotated[
        SnapshotTimeframe,
        typer.Option(
            "--timeframe",
            help="Snapshot granularity",
        ),
    ],
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
            help="Output raw API response without normalization",
        ),
    ] = False,
) -> None:
    """Show type-scoped net-value snapshots from a start date.

    Month-timeframe periods retain their upstream ``YYYY-MM`` precision (no
    day component is appended); year-timeframe periods keep their upstream
    yearly form. There is no end-date filter in the released capability.

    This command is read-only and never modifies remote state.

    Examples:
        monarch accounts snapshots-by-type -s 2023-01-01 --timeframe month --json
        monarch accounts snapshots-by-type -s 2020-01-01 --timeframe year
    """
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching type-scoped snapshots..."):
        data: Any = get_account_snapshots_by_type(start, timeframe.value, raw=raw)

    output(data, output_format, raw=False)


@app.command("refresh-status")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def refresh_status(
    account: Annotated[
        list[str] | None,
        typer.Option(
            "-a",
            "--account",
            help=(
                "Specific account ID(s) to check (repeatable). Checks all accounts when omitted."
            ),
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
) -> None:
    """Observationally inspect account refresh completion.

    Reports whether accounts are still synchronizing. This never initiates,
    polls, or waits for a refresh; use 'accounts refresh' (a remote mutation)
    to request one. Requested account IDs are validated against account
    discovery first: unknown IDs are reported explicitly and never produce a
    'complete: true' result.

    The result has documented stable keys: ``status``
    (``complete``/``in_progress``/``unknown``), ``complete`` (boolean or
    ``null`` when unknown), ``requested_account_ids``,
    ``known_account_ids``, ``unknown_account_ids``, and
    ``checked_account_count``.

    This command is read-only and never modifies remote state.

    Examples:
        monarch accounts refresh-status --json
        monarch accounts refresh-status -a ACC123 -a ACC456 --json
    """
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Checking refresh status..."):
        result = get_refresh_status(list(account) if account else None)

    output(result, output_format, raw=False)


@app.command()
@handle_errors
@operation_effects(Effect.REMOTE_MUTATION)
def refresh(
    account: Annotated[
        list[str] | None,
        typer.Option(
            "-a",
            "--account",
            help="Specific account ID(s) to refresh (repeatable). Refreshes all if not provided.",
        ),
    ] = None,
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
    account_ids = list(account) if account else None

    # Authorize before authentication lookup, client creation, or any prompt.
    operation = Operation(command="accounts refresh", effects=frozenset({Effect.REMOTE_MUTATION}))
    require_mutation_authorization(operation)

    with spinner("Requesting account refresh..."):
        result = refresh_accounts(account_ids, operation=operation)

    output(result)

    # All-succeeded outcomes exit 0; ambiguous outcomes exit 4 with the
    # required verification object in the envelope. Definitive failures exit
    # with the normal operation/API nonzero code. The no_accounts notice is
    # a pre-execution result, not a mutation outcome, and exits 0.
    if result.get("schema_version") == "mutation-outcome.v1":
        code = outcome_exit_code(result["status"])
        if code:
            raise typer.Exit(code)
