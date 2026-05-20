"""Account commands for Monarch CLI."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from monarchmoney.monarchmoney import BalanceHistoryRow  # type: ignore[import-untyped]

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.accounts import list_accounts, refresh_accounts

app = typer.Typer(
    help="Account management",
    no_args_is_help=True,
)


def _resolve_format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    """Resolve explicit output flags."""
    return OutputFormat.JSON if json_output else format


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
        if wait:
            client = get_authenticated_client()
            complete: bool = run_api_call(
                lambda: client.request_accounts_refresh_and_wait(
                    account_ids=account_ids,
                    timeout=timeout,
                    delay=delay,
                ),
                timeout_seconds=timeout + delay,
                max_retries=0,
            )
            result = {
                "status": "complete" if complete else "timeout",
                "complete": complete,
                "account_ids": account_ids,
            }
        else:
            result = refresh_accounts(account_ids)

    output(result)


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
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Check whether account refresh is complete."""
    account_ids = list(account) if account else None
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
    output(data, _resolve_format(format, json_output))


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
        output({"status": "error", "message": "No account changes specified."})
        raise typer.Exit(1)

    with spinner("Updating account..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.update_account(account_id=account_id, **changes))
    output(data, _resolve_format(format, json_output))


@app.command("delete")
@handle_errors
def delete(
    account_id: Annotated[str, typer.Argument(help="Account ID to delete")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm account deletion")] = False,
) -> None:
    """Delete an account."""
    if not yes:
        output({"status": "error", "message": "Account delete requires --yes."})
        raise typer.Exit(1)

    with spinner("Deleting account..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.delete_account(account_id=account_id))
    output({"status": "deleted", "account_id": account_id, "result": data})


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
        {"status": "uploaded" if success else "failed", "account_id": account_id, "rows": len(rows)}
    )
