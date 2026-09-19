"""Read-only investment commands."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..core.error_handler import handle_errors
from ..core.exceptions import ValidationError
from ..core.operations import Effect, operation_effects
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.investments import get_investment_holdings

app = typer.Typer(help="Investment holdings", no_args_is_help=True)


@app.command("holdings")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def holdings_cmd(
    account: Annotated[
        list[str] | None,
        typer.Option("-a", "--account", help="Opaque account ID (repeatable)."),
    ] = None,
    include_hidden: Annotated[
        bool,
        typer.Option(
            "--include-hidden",
            help="Include hidden eligible accounts during automatic discovery.",
        ),
    ] = False,
    aggregate: Annotated[
        bool,
        typer.Option(
            "--aggregate",
            help="Group rows by non-null upstream security ID without monetary totals.",
        ),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Return a deterministic account-ID keyed raw response envelope.",
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
) -> None:
    """List normalized holdings across eligible investment accounts.

    Discovery runs once. Visible eligible accounts with a reported positive
    holdings count are selected by default; ``--include-hidden`` opts hidden
    accounts into automatic discovery. Repeated ``--account`` options select
    known accounts explicitly, including hidden accounts, and validate their
    eligibility before any holdings request. At most four holdings reads run
    concurrently, using the shared read timeout/retry policy.

    ``--aggregate`` groups only rows sharing a non-null security ID. It sums
    quantity only when every quantity is present and keeps monetary values in
    per-account contributions because the released API exposes no currency
    metadata. ``--raw`` returns account-ID keyed raw payloads and bypasses
    normalization and aggregation.

    Examples:
        monarch investments holdings --json
        monarch investments holdings --include-hidden --format table
        monarch investments holdings --account ACC123 --account ACC456 --json
        monarch investments holdings --aggregate --json
        monarch investments holdings --raw --json
    """
    output_format = OutputFormat.JSON if json_output else format
    if raw and aggregate:
        raise ValidationError(
            "--aggregate only shapes normalized output and is incompatible with "
            "--raw; the raw response bypasses normalization and aggregation.",
            field="aggregate",
            details={"incompatible_with": "raw"},
        )
    with spinner("Fetching investment holdings..."):
        data: Any = get_investment_holdings(
            list(account) if account else None,
            include_hidden=include_hidden,
            aggregate=aggregate,
            raw=raw,
        )
    output(data, output_format)
