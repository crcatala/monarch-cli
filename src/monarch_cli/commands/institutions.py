"""Institution and credential connection diagnostics commands."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..core.error_handler import handle_errors
from ..core.operations import Effect, operation_effects
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.institutions import (
    INSTITUTIONS_OPERATION,
    get_institutions_raw,
    list_institutions,
)

app = typer.Typer(help="Institution connection diagnostics", no_args_is_help=True)


def _format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    return OutputFormat.JSON if json_output else format


@app.command("list")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def list_cmd(
    include_deleted: Annotated[
        bool,
        typer.Option(
            "--include-deleted",
            help="Include deleted accounts and retain their deletion state.",
        ),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON (shortcut for --format json)"),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Preserve the complete upstream response, including embedded subscription data.",
        ),
    ] = False,
) -> None:
    """List credential-centric institution connection status.

    Normalized output groups associated accounts under each credential. Deleted
    accounts are excluded by default; use ``--include-deleted`` when auditing
    historical records. Missing connection fields remain null and never imply
    a healthy connection. This command is read-only.
    """
    with spinner("Fetching institutions..."):
        data: Any = (
            get_institutions_raw(INSTITUTIONS_OPERATION)
            if raw
            else list_institutions(
                include_deleted=include_deleted,
                operation=INSTITUTIONS_OPERATION,
            )
        )
    output(data, _format(format, json_output))
