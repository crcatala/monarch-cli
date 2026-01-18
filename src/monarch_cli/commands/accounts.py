"""Account commands for Monarch CLI."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.accounts import list_accounts, refresh_accounts

app = typer.Typer(
    help="Account management",
    no_args_is_help=True,
)


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
            data: Any = run_async(client.get_accounts())
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

    with spinner("Requesting account refresh..."):
        result = refresh_accounts(account_ids)

    output(result)
