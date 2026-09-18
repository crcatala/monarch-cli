"""Cashflow commands for Monarch CLI."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.dates import (
    DatePreset,
    parse_date_range,
    parse_iso_date,
    validate_date_ordering,
)
from ..core.error_handler import handle_errors
from ..core.exceptions import ValidationError
from ..core.operations import Effect, Operation, operation_effects, run_read_call
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.cashflow import transform_cashflow_detail, transform_cashflow_summary

app = typer.Typer(
    help="Cashflow analysis",
    no_args_is_help=True,
)


def _parse_date(date_str: str | None) -> date | None:
    """Parse a date for backwards-compatible direct callers.

    Command execution uses the shared strict parser directly; this wrapper
    retains the historical ``typer.BadParameter`` behavior for callers of the
    module helper.
    """
    if date_str is None:
        return None
    try:
        return parse_iso_date(date_str, field="date")
    except ValidationError as e:
        raise typer.BadParameter(e.message) from e


def _resolve_date_range(
    preset: DatePreset | None,
    start: str | None,
    end: str | None,
) -> tuple[str | None, str | None]:
    """Resolve cashflow dates with the released API's two-sided rule."""
    # A preset may provide both bounds, but a caller-supplied explicit range
    # is either complete or rejected. This prevents an API call for a range
    # whose meaning depends on undocumented one-sided behavior.
    if (start is None) != (end is None):
        raise ValidationError(
            message="--start and --end must be provided together.",
            field="start" if start is not None else "end",
        )

    start_date = parse_iso_date(start, field="start")
    end_date = parse_iso_date(end, field="end")
    validate_date_ordering(start_date, end_date)
    return parse_date_range(preset, start_date, end_date)


def _output_format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    """Apply the command-local JSON shortcut."""
    return OutputFormat.JSON if json_output else format


@app.command("summary")
@handle_errors
@operation_effects(Effect.READ_ONLY)
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
    output_format = _output_format(format, json_output)
    start_str, end_str = _resolve_date_range(preset, start, end)

    with spinner("Calculating cashflow..."):
        client = get_authenticated_client()
        data: Any = run_read_call(
            lambda: client.get_cashflow_summary(
                start_date=start_str,
                end_date=end_str,
            ),
            Operation(command="cashflow summary", effects=frozenset({Effect.READ_ONLY})),
        )

    output(transform_cashflow_summary(data), output_format)


@app.command("detail")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def detail(
    start: Annotated[
        str | None,
        typer.Option("-s", "--start", help="Start date filter (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("-e", "--end", help="End date filter (YYYY-MM-DD)"),
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
        typer.Option("--json", help="Output as JSON (shortcut for --format json)"),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option("--raw", help="Output the upstream response without normalization"),
    ] = False,
) -> None:
    """Get category, category-group, merchant, and overall cashflow detail.

    The aggregate response is returned as one non-paginated result. It uses
    the same inclusive date and preset semantics as ``cashflow summary``.

    Examples:
        monarch cashflow detail
        monarch cashflow detail --preset this-month --json
        monarch cashflow detail -s 2024-01-01 -e 2024-12-31
        monarch cashflow detail --raw  # Preserve the upstream response
    """
    output_format = _output_format(format, json_output)
    start_str, end_str = _resolve_date_range(preset, start, end)

    with spinner("Calculating cashflow detail..."):
        client = get_authenticated_client()
        data: Any = run_read_call(
            lambda: client.get_cashflow(
                start_date=start_str,
                end_date=end_str,
            ),
            Operation(command="cashflow detail", effects=frozenset({Effect.READ_ONLY})),
        )

    normalized = data if raw else transform_cashflow_detail(data)
    # Raw data still uses the selected formatter (JSON remains valid JSON).
    output(normalized, output_format)
