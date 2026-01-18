"""Monarch CLI entry point."""

import typer

from monarch_cli import __version__
from monarch_cli.commands import auth

app = typer.Typer(name="monarch", help="CLI for Monarch Money", no_args_is_help=True)

# Register command groups
app.add_typer(auth.app, name="auth")


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
) -> None:
    """CLI for Monarch Money - AI-agent friendly financial data access."""


if __name__ == "__main__":
    app()
