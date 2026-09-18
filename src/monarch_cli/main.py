"""Monarch CLI entry point."""

import typer

from monarch_cli import __version__
from monarch_cli.commands import (
    accounts,
    auth,
    budgets,
    cashflow,
    categories,
    institutions,
    subscription,
    transactions,
)
from monarch_cli.core.config import get_config, set_config
from monarch_cli.core.operations import set_mutation_authorized
from monarch_cli.core.prompting import resolve_non_interactive, set_non_interactive
from monarch_cli.output import apply_config

app = typer.Typer(name="monarch", help="CLI for Monarch Money", no_args_is_help=True)

# Register command groups
app.add_typer(auth.app, name="auth")
app.add_typer(accounts.app, name="accounts")
app.add_typer(transactions.app, name="transactions")
app.add_typer(budgets.app, name="budgets")
app.add_typer(cashflow.app, name="cashflow")
app.add_typer(categories.app, name="categories")
app.add_typer(institutions.app, name="institutions")
app.add_typer(subscription.app, name="subscription")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"monarch-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(  # noqa: ARG001
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Show operational progress messages.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show stack traces on errors (implies --verbose).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format (overrides TTY detection).",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Output only IDs, one per line (for AI agent consumption).",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output.",
    ),
    timeout: int | None = typer.Option(
        None,
        "--timeout",
        help="API request timeout in seconds.",
    ),
    allow_mutations: bool = typer.Option(
        False,
        "--allow-mutations",
        help=(
            "Authorize remote mutations for this invocation only. "
            "Must appear before the command path; never persisted to config "
            "or read from the environment."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip shared destructive confirmation for this invocation.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help=(
            "Fail with a structured error instead of prompting whenever input "
            "would be read (email, password, MFA code, storage choice, "
            "confirmation). Also enabled by MONARCH_NON_INTERACTIVE=1 or "
            "config non_interactive=true. Never authorizes mutations or "
            "auto-answers confirmations."
        ),
    ),
) -> None:
    """CLI for Monarch Money - AI-agent friendly financial data access."""
    # Per-invocation mutation authorization (mc-k48z). Read-only by default;
    # no config-file or environment-variable authorization is supported.
    set_mutation_authorized(allow_mutations)

    # Load config from file and env vars
    config = get_config()

    # Shared non-interactive prompt policy (mc-2btg): CLI flag OR the
    # automation-friendly config sources (MONARCH_NON_INTERACTIVE env var or
    # the non_interactive config-file key).
    set_non_interactive(resolve_non_interactive(non_interactive))

    # Apply CLI flag overrides
    config = config.with_overrides(
        verbose=verbose if verbose else None,
        debug=debug if debug else None,
        format="json" if json_output else None,
        quiet=quiet if quiet else None,
        color=False if no_color else None,
        timeout_seconds=timeout,
        confirm_destructive=False if yes else None,
    )

    # Set the global config with overrides applied
    set_config(config)

    # Apply config to output system
    apply_config(config)


if __name__ == "__main__":
    app()
