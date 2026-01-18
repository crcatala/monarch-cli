"""Cashflow commands for Monarch CLI."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.dates import DatePreset, parse_date_range
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner

app = typer.Typer(
    help="Cashflow analysis",
    no_args_is_help=True,
)


def _parse_date(date_str: str | None) -> date | None:
    """Parse a date string in YYYY-MM-DD format."""
    if date_str is None:
        return None
    return date.fromisoformat(date_str)


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
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    # Parse date range (preset + explicit dates)
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    start_str, end_str = parse_date_range(preset, start_date, end_date)

    with spinner("Calculating cashflow..."):
        client = get_authenticated_client()
        data: Any = run_async(
            client.get_cashflow_summary(
                start_date=start_str,
                end_date=end_str,
            )
        )

    output(data, output_format)
