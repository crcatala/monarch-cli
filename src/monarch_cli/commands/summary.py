"""High-level financial summary command."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.cashflow import transform_cashflow_summary
from ..transformers.net_worth import transform_net_worth

app = typer.Typer(help="Net worth and month-to-date cashflow", no_args_is_help=False)


@app.command()
@handle_errors
def show(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show a compact financial snapshot."""
    today = date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()

    with spinner("Building financial summary..."):
        client = get_authenticated_client()
        accounts: dict[str, Any] = run_api_call(lambda: client.get_accounts())
        cashflow: dict[str, Any] = run_api_call(
            lambda: client.get_cashflow_summary(start_date=start, end_date=end)
        )

    result: dict[str, Any] = transform_net_worth(accounts)
    result["cashflow_period"] = {"start": start, "end": end}
    result["cashflow"] = transform_cashflow_summary(cashflow)
    output(result, OutputFormat.JSON if json_output else format)
