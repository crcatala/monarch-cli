"""Help contract tests (mc-4z49).

Help generation must be safe (no credential lookup, prompt, or network) and
every remote mutation must document that the global ``--allow-mutations``
option is required *before* the command path, plus ``--dry-run`` where the
command supports it. The mutation set is driven by the shared operation
inventory so future mutations are covered automatically.
"""

from __future__ import annotations

import re

import typer.main
from typer.testing import CliRunner

from monarch_cli.core.operations import Effect, collect_command_effects
from monarch_cli.main import app

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# A wide terminal keeps help text from wrapping option names/phrases.
_ENV = {"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"}


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def _invoke_help(path: list[str]):  # noqa: ANN202
    return runner.invoke(app, [*path, "--help"], env=_ENV)


def _click_command(path: list[str]):  # noqa: ANN202
    node = typer.main.get_command(app)
    for part in path:
        node = node.commands[part]
    return node


def _mutation_commands() -> list[str]:
    inventory = collect_command_effects(app)
    return sorted(
        command for command, effects in inventory.items() if Effect.REMOTE_MUTATION in effects
    )


def test_inventory_is_non_empty() -> None:
    commands = _mutation_commands()
    assert commands, "expected at least one remote mutation command in the inventory"
    assert "transactions tags add" in commands


def test_every_mutation_help_documents_authorization_and_placement() -> None:
    for command in _mutation_commands():
        path = command.split()
        result = _invoke_help(path)
        out = _plain(result.stdout + (result.stderr or ""))
        assert result.exit_code == 0, (command, out)
        assert "--allow-mutations" in out, f"{command} help omits --allow-mutations"
        assert "before the command path" in out, (
            f"{command} help omits the global placement guidance"
        )
        node = _click_command(path)
        has_dry_run = any("--dry-run" in getattr(param, "opts", []) for param in node.params)
        if has_dry_run:
            assert "--dry-run" in out, f"{command} supports --dry-run but help omits it"


def test_root_help_lists_groups_and_global_options() -> None:
    result = _invoke_help([])
    out = _plain(result.stdout)
    assert result.exit_code == 0
    for group in ("auth", "accounts", "transactions", "investments"):
        assert group in out
    for option in ("--json", "--quiet", "--allow-mutations", "--non-interactive"):
        assert option in out


def test_representative_commands_document_examples() -> None:
    for path in (
        ["accounts", "list"],
        ["transactions", "list"],
        ["auth", "login"],
        ["transactions", "tags", "add"],
    ):
        result = _invoke_help(path)
        out = _plain(result.stdout)
        assert result.exit_code == 0, path
        assert "Examples:" in out, path


def test_help_does_not_lookup_credentials_or_prompt() -> None:
    from unittest.mock import patch

    with (
        patch(
            "monarch_cli.core.adapter.get_authenticated_client",
            side_effect=AssertionError("help must not look up credentials"),
        ),
        patch(
            "monarch_cli.core.prompting.prompt_text",
            side_effect=AssertionError("help must not prompt"),
        ),
    ):
        result = _invoke_help(["transactions", "tags", "add"])
        auth_result = _invoke_help(["auth", "login"])

    assert result.exit_code == 0
    assert auth_result.exit_code == 0
