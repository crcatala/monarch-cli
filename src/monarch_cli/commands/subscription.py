"""Subscription entitlement command."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..core.error_handler import handle_errors
from ..core.operations import Effect, operation_effects
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..services.institutions import SUBSCRIPTION_OPERATION, get_subscription_raw, show_subscription

app = typer.Typer(help="Subscription entitlement status", no_args_is_help=True)


def _format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    return OutputFormat.JSON if json_output else format


@app.command("show")
@handle_errors
@operation_effects(Effect.READ_ONLY)
def show(
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
            help="Preserve the complete upstream response, including payment/referral fields.",
        ),
    ] = False,
) -> None:
    """Show normalized trial and premium-entitlement state.

    ``available: false`` means the upstream subscription object was absent or
    lacked usable trial/entitlement booleans; this is distinct from an
    available subscription reporting false booleans. Normalized output
    intentionally excludes referral and payment-source data.
    This command is read-only.
    """
    with spinner("Fetching subscription..."):
        data: Any = (
            get_subscription_raw(SUBSCRIPTION_OPERATION)
            if raw
            else show_subscription(SUBSCRIPTION_OPERATION)
        )
    output(data, _format(format, json_output))
