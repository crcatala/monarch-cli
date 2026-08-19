"""Recurring transaction command."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.recurring import transform_recurring

app = typer.Typer(help="Upcoming recurring transactions", no_args_is_help=False)


def _parse_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid date format: '{value}'. Use YYYY-MM-DD.") from exc


@app.command("list")
@handle_errors
def list_cmd(
    start: Annotated[
        str | None,
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List upcoming recurring charges and income."""
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if (start_date is None) != (end_date is None):
        raise typer.BadParameter("--start and --end must be provided together")

    with spinner("Fetching recurring transactions..."):
        client = get_authenticated_client()
        raw: dict[str, Any] = run_api_call(
            lambda: client.get_recurring_transactions(
                start_date=start_date,
                end_date=end_date,
            )
        )
    output(
        transform_recurring(raw),
        OutputFormat.JSON if json_output else format,
    )
