"""Monarch CLI entry point."""

import typer

from monarch_cli import __version__
from monarch_cli.commands import accounts, auth, budgets, cashflow, categories, transactions
from monarch_cli.output import OutputFormat, set_debug, set_default_format, set_quiet, set_verbose
from monarch_cli.output.plain import set_color_enabled

app = typer.Typer(name="monarch", help="CLI for Monarch Money", no_args_is_help=True)

# Register command groups
app.add_typer(auth.app, name="auth")
app.add_typer(accounts.app, name="accounts")
app.add_typer(transactions.app, name="transactions")
app.add_typer(budgets.app, name="budgets")
app.add_typer(cashflow.app, name="cashflow")
app.add_typer(categories.app, name="categories")


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
) -> None:
    """CLI for Monarch Money - AI-agent friendly financial data access."""
    if verbose:
        set_verbose(True)
    if debug:
        set_debug(True)
    if json_output:
        set_default_format(OutputFormat.JSON)
    if quiet:
        set_quiet(True)
    if no_color:
        set_color_enabled(False)


if __name__ == "__main__":
    app()
