"""Cashflow commands for Monarch CLI."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.dates import DatePreset, parse_date_range
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.cashflow import transform_cashflow_summary

app = typer.Typer(
    help=(
        "Cashflow analysis\n\nExamples:\n"
        "    monarch cashflow summary\n"
        "    monarch cashflow summary --preset this-month"
    ),
    no_args_is_help=False,
    invoke_without_command=True,
)


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


def _resolve_format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    """Resolve explicit output flags."""
    return OutputFormat.JSON if json_output else format


def _date_range(
    start: str | None, end: str | None, preset: DatePreset | None
) -> tuple[str | None, str | None]:
    """Parse CLI date options into API date strings."""
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    return parse_date_range(preset, start_date, end_date)


def _summary(
    *,
    start: str | None,
    end: str | None,
    preset: DatePreset | None,
    format: OutputFormat | None,
    json_output: bool,
) -> None:
    """Fetch and output cashflow summary."""
    output_format = _resolve_format(format, json_output)
    start_str, end_str = _date_range(start, end, preset)

    with spinner("Calculating cashflow..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.get_cashflow_summary(
                start_date=start_str,
                end_date=end_str,
            )
        )

    transformed = transform_cashflow_summary(data)
    output(transformed, output_format)


@app.callback()
@handle_errors
def main(
    ctx: typer.Context,
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
            help="Date range preset (e.g., this-month, last-30-days, ytd)",
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
    """Get income/expense analysis for a date range."""
    if ctx.invoked_subcommand is None:
        _summary(start=start, end=end, preset=preset, format=format, json_output=json_output)


@app.command("summary")
@handle_errors
def summary(
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
            help="Date range preset (e.g., this-month, last-30-days, ytd)",
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
    """Get income/expense analysis for a date range.

    Shows total income, expenses, savings, and savings rate for the
    specified period. Use presets for common ranges or explicit dates.

    Examples:
        monarch cashflow summary                      # Current period
        monarch cashflow summary --preset this-month  # This month
        monarch cashflow summary --preset last-30-days  # Last 30 days
        monarch cashflow summary --preset ytd         # Year to date
        monarch cashflow summary -s 2024-01-01 -e 2024-12-31  # Date range
        monarch cashflow summary --format table       # Table format
        monarch cashflow summary | jq .              # Auto-JSON when piped
    """
    _summary(start=start, end=end, preset=preset, format=format, json_output=json_output)


@app.command("detail")
@handle_errors
def detail(
    limit: Annotated[int, typer.Option("-l", "--limit", help="Maximum rows to return")] = 100,
    start: Annotated[str | None, typer.Option("-s", "--start", help="Start date")] = None,
    end: Annotated[str | None, typer.Option("-e", "--end", help="End date")] = None,
    preset: Annotated[
        DatePreset | None,
        typer.Option("-p", "--preset", help="Date range preset"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Fetch detailed cashflow breakdown."""
    start_str, end_str = _date_range(start, end, preset)
    with spinner("Fetching cashflow details..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.get_cashflow(limit=limit, start_date=start_str, end_date=end_str)
        )
    output(data, _resolve_format(format, json_output))


@app.command("transaction-summary")
@handle_errors
def transaction_summary(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get transaction summary data from the transactions page."""
    with spinner("Fetching transaction summary..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_transactions_summary())
    output(data, _resolve_format(format, json_output))


@app.command("recurring")
@handle_errors
def recurring(
    start: Annotated[str | None, typer.Option("-s", "--start", help="Start date")] = None,
    end: Annotated[str | None, typer.Option("-e", "--end", help="End date")] = None,
    preset: Annotated[
        DatePreset | None,
        typer.Option("-p", "--preset", help="Date range preset"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get recurring transactions."""
    start_str, end_str = _date_range(start, end, preset)
    with spinner("Fetching recurring transactions..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.get_recurring_transactions(start_date=start_str, end_date=end_str)
        )
    output(data, _resolve_format(format, json_output))


@app.command("credit-history")
@handle_errors
def credit_history(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get credit history."""
    with spinner("Fetching credit history..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_credit_history())
    output(data, _resolve_format(format, json_output))


@app.command("subscription")
@handle_errors
def subscription(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get subscription/account-plan details."""
    with spinner("Fetching subscription details..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_subscription_details())
    output(data, _resolve_format(format, json_output))


@app.command("institutions")
@handle_errors
def institutions(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get linked institutions."""
    with spinner("Fetching institutions..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_institutions())
    output(data, _resolve_format(format, json_output))
