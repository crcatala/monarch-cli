"""``monarch update`` command.

Thin Typer wiring around the release-standard ``cli_meta`` module, which owns
the install-method detection and the actual upgrade steps. The command never
touches financial data or credentials: it updates the local installation the
way it was installed (source checkout, ``uv tool``, ``pipx``, ``pip``, or
``mise``) and reports what it would run before running it.
"""

from __future__ import annotations

import typer

from .. import cli_meta
from ..core.error_handler import handle_errors
from ..core.operations import Effect, operation_effects


@handle_errors
@operation_effects(Effect.LOCAL_INSTALL_CHANGE)
def update(
    check: bool = typer.Option(
        False,
        "--check",
        help=(
            "Report whether an update is available without changing anything. "
            "Exit 0 when up to date, 1 when an update is available, 2 when unknown."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Update even when the install already looks current.",
    ),
) -> None:
    """Update monarch with the method it was installed with.

    A source checkout updates from ``origin/main`` with ``git pull --ff-only``
    and a reinstall, and refuses a dirty tree or a branch other than ``main``.
    Package-manager installs run that package manager's upgrade command.

    Examples:
        monarch update --check
        monarch update
        monarch update --force
    """
    raise typer.Exit(cli_meta.run_update("monarch", "monarch-cli", check=check, force=force))


__all__ = ["update"]
