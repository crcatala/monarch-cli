"""Net-worth command."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.net_worth import transform_net_worth

app = typer.Typer(help="Current net worth", no_args_is_help=False)


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
    """Show assets, liabilities, and net worth from included accounts."""
    output_format = OutputFormat.JSON if json_output else format
    with spinner("Calculating net worth..."):
        client = get_authenticated_client()
        raw: dict[str, Any] = run_api_call(lambda: client.get_accounts())
    output(transform_net_worth(raw), output_format)
