"""Authentication commands for Monarch CLI."""

import typer

app = typer.Typer(
    help="Authentication management",
    no_args_is_help=True,
)


@app.command()
def login() -> None:
    """Log in to Monarch Money."""
    # Placeholder - full implementation in next task
    typer.echo("Login not yet implemented")


@app.command()
def status() -> None:
    """Show current authentication status."""
    # Placeholder - full implementation in next task
    typer.echo("Status not yet implemented")


@app.command()
def logout() -> None:
    """Log out and clear stored credentials."""
    # Placeholder - full implementation in next task
    typer.echo("Logout not yet implemented")


@app.command()
def doctor() -> None:
    """Diagnose authentication setup."""
    # Placeholder - full implementation in next task
    typer.echo("Doctor not yet implemented")


@app.command()
def ping() -> None:
    """Test API connectivity."""
    # Placeholder - full implementation in next task
    typer.echo("Ping not yet implemented")


@app.command()
def setup() -> None:
    """Show setup instructions."""
    # Placeholder - full implementation in next task
    typer.echo("Setup not yet implemented")
