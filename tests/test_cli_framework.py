"""Framework-sensitive CLI contract tests (mc-43s0).

These tests pin the CLI behavior that a Typer/framework upgrade could silently
change: command registration in the root help, nested command registration,
global and nested option parsing, list-argument parsing, and error paths.

They are the "compatibility suite" referenced by the Typer bound in
``pyproject.toml`` (``typer>=0.27.1,<0.28``): widening the supported minor range
requires re-running this suite against the lower and latest candidate versions.

They deliberately avoid the network and credentials; commands are either help
paths or point at mocked clients.
"""

from __future__ import annotations

import json
import re
import warnings
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli import output as cli_output
from monarch_cli.core.config import reset_config
from monarch_cli.main import app

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typer.testing import Result

runner = CliRunner()

#: Command groups registered on the root app.
COMMAND_GROUPS = (
    "auth",
    "accounts",
    "transactions",
    "budgets",
    "cashflow",
    "categories",
)

#: Representative commands that must remain registered under each group.
NESTED_COMMANDS: dict[str, tuple[str, ...]] = {
    "auth": ("login", "status", "logout", "doctor", "ping", "setup"),
    "accounts": ("list", "refresh"),
    "transactions": ("list", "update", "batch-update"),
    "budgets": ("list",),
    "cashflow": ("summary", "detail"),
    "categories": ("list",),
}

#: Global options that must remain registered on the root callback.
GLOBAL_OPTIONS = (
    "--version",
    "--verbose",
    "--debug",
    "--json",
    "--quiet",
    "--no-color",
    "--timeout",
    "--allow-mutations",
    "--yes",
    "--non-interactive",
)


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the root callback from reading or writing the real user config."""
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MONARCH_TOKEN", raising=False)


ANSI_ESCAPE_RE = re.compile(rb"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def reset_output_state() -> None:
    """Reset module-level state mutated by global CLI options.

    The root callback persists a global ``Config`` carrying ``--quiet``/
    ``--verbose``/``--json``/``--no-color`` overrides and mirrors them into
    ``monarch_cli.output`` module globals; without a reset those leak into
    later tests (quiet mode suppresses non-ID payloads entirely).
    """
    yield
    reset_config()
    cli_output.set_verbose(False)
    cli_output.set_debug(False)
    cli_output.set_quiet(False)
    cli_output.set_default_format(None)
    cli_output.set_color_enabled(None)


def invoke(args: Sequence[str]) -> tuple[Result, list[warnings.WarningMessage]]:
    """Invoke the CLI, capturing both the result and any emitted warnings.

    Rich styling is stripped from the captured output so assertions match the
    rendered text rather than ANSI-escaped fragments (the default theme splits
    strings like ``--version`` across escape sequences).
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = runner.invoke(app, list(args))
    result.stdout_bytes = ANSI_ESCAPE_RE.sub(b"", result.stdout_bytes)
    result.output_bytes = ANSI_ESCAPE_RE.sub(b"", result.output_bytes)
    return result, list(caught)


def assert_parsed_cleanly(result: Result, caught: list[warnings.WarningMessage]) -> None:
    """Assert a command parsed and ran without warnings, tracebacks, or crashes.

    A non-zero exit code is allowed (error paths are expected to set one); what
    must never happen is an unhandled exception, a deprecation/framework
    warning, or an "unknown option" style parse failure.
    """
    assert "Traceback (most recent call last)" not in result.output, result.output
    assert "unexpected keyword argument" not in result.output, result.output
    assert "Got unexpected extra" not in result.output, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"unexpected exception: {result.exception!r}"
    )
    emitted = [f"{w.category.__name__}: {w.message}" for w in caught]
    assert emitted == [], emitted


class TestRootHelp:
    """Root help must expose every registered command group and global option."""

    def test_root_help_lists_all_command_groups(self) -> None:
        result, caught = invoke(["--help"])

        assert result.exit_code == 0
        assert_parsed_cleanly(result, caught)
        for group in COMMAND_GROUPS:
            assert group in result.output, f"missing command group: {group}"

    def test_root_help_lists_global_options(self) -> None:
        result, caught = invoke(["--help"])

        assert result.exit_code == 0
        assert_parsed_cleanly(result, caught)
        for option in GLOBAL_OPTIONS:
            assert option in result.output, f"missing global option: {option}"

    def test_no_args_shows_help(self) -> None:
        result, caught = invoke([])

        # no_args_is_help=True exits non-zero but must print the command list.
        assert_parsed_cleanly(result, caught)
        for group in COMMAND_GROUPS:
            assert group in result.output


class TestNestedHelp:
    """Nested help must keep representative commands registered."""

    @pytest.mark.parametrize("group", COMMAND_GROUPS)
    def test_group_help_lists_representative_commands(self, group: str) -> None:
        result, caught = invoke([group, "--help"])

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        for command in NESTED_COMMANDS[group]:
            assert command in result.output, f"missing command '{command}' in '{group}'"

    @pytest.mark.parametrize(
        ("group", "command"),
        [(group, command) for group, cmds in NESTED_COMMANDS.items() for command in cmds],
    )
    def test_nested_command_help_renders(self, group: str, command: str) -> None:
        result, caught = invoke([group, command, "--help"])

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        assert "Usage:" in result.output


class TestGlobalOptionParsing:
    """Global options must still parse in front of a nested command."""

    def test_version_flag(self) -> None:
        for flag in ("--version", "-v"):
            result, caught = invoke([flag])

            assert result.exit_code == 0, result.output
            assert_parsed_cleanly(result, caught)
            assert "monarch-cli" in result.output

    def test_global_options_parse_before_subcommand(self) -> None:
        storage_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "none",
        }
        with patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=storage_info,
        ):
            result, caught = invoke(
                [
                    "--no-color",
                    "--verbose",
                    "--timeout",
                    "5",
                    "auth",
                    "status",
                ]
            )

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)

    def test_global_options_after_subcommand(self) -> None:
        """Global-only options placed after the command path are rejected.

        The documented grammar is ``monarch [GLOBAL OPTIONS] GROUP COMMAND
        [COMMAND OPTIONS]``. A root-only global option such as
        ``--allow-mutations`` is not a command option, so placing it after the
        command path must be a usage error rather than silently accepted.
        """
        result, caught = invoke(["auth", "status", "--allow-mutations"])

        assert result.exit_code != 0
        assert_parsed_cleanly(result, caught)
        assert "--allow-mutations" in result.output

    def test_global_options_placement_before_subcommand_is_effective(self) -> None:
        """A root global option before the command path still takes effect."""
        storage_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": None,
        }
        with patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=storage_info,
        ):
            result, caught = invoke(["--json", "auth", "status"])

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        data = json.loads(result.output)
        assert data["authenticated"] is False

    def test_root_json_matches_local_json_for_auth_status(self) -> None:
        """`monarch --json auth status` and `monarch auth status --json` agree."""
        storage_info = {
            "has_env_token": False,
            "has_keyring_token": True,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "keyring",
        }
        with patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=storage_info,
        ):
            root_result, root_caught = invoke(["--json", "auth", "status"])
            local_result, local_caught = invoke(["auth", "status", "--json"])

        assert_parsed_cleanly(root_result, root_caught)
        assert_parsed_cleanly(local_result, local_caught)
        assert root_result.exit_code == 0, root_result.output
        assert local_result.exit_code == 0, local_result.output
        assert json.loads(root_result.output) == json.loads(local_result.output)

    def test_invalid_timeout_value_is_a_parse_error(self) -> None:
        result, caught = invoke(["--timeout", "not-a-number", "auth", "status"])

        assert result.exit_code != 0
        assert_parsed_cleanly(result, caught)
        assert "Traceback" not in result.output


class TestNestedOptionAndArgumentParsing:
    """Nested options, list options, and list arguments must parse cleanly."""

    def _mock_client(self) -> tuple[MagicMock, dict]:
        captured: dict = {}
        client = MagicMock()

        async def async_get_transactions(**kwargs):
            captured.update(kwargs)
            return {"allTransactions": {"results": [], "totalCount": 0}}

        client.get_transactions = async_get_transactions
        return client, captured

    def test_transactions_list_parses_options(self) -> None:
        client, captured = self._mock_client()
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result, caught = invoke(
                [
                    "transactions",
                    "list",
                    "--limit",
                    "5",
                    "--offset",
                    "10",
                    "--start",
                    "2024-01-01",
                    "--end",
                    "2024-01-31",
                    "--search",
                    "coffee",
                    "--json",
                ]
            )

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        assert captured["limit"] == 5
        assert captured["offset"] == 10

    def test_transactions_list_parses_repeatable_list_option(self) -> None:
        client, captured = self._mock_client()
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result, caught = invoke(
                [
                    "transactions",
                    "list",
                    "-a",
                    "acc_123",
                    "-a",
                    "acc_456",
                    "--json",
                ]
            )

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        assert captured["account_ids"] == ["acc_123", "acc_456"]

    def test_batch_update_parses_repeatable_option_list(self) -> None:
        result, caught = invoke(
            [
                "transactions",
                "batch-update",
                "--transaction-id",
                "txn_1",
                "--transaction-id",
                "txn_2",
                "--transaction-id",
                "txn_3",
                "--notes",
                "framework check",
                "--dry-run",
            ]
        )

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        assert "txn_3" in result.output


class TestErrorPaths:
    """Error paths must exit cleanly rather than raising framework errors."""

    def test_unknown_command_is_a_usage_error(self) -> None:
        result, caught = invoke(["not-a-command"])

        assert result.exit_code != 0
        assert_parsed_cleanly(result, caught)
        assert "Traceback" not in result.output

    def test_unknown_nested_command_is_a_usage_error(self) -> None:
        result, caught = invoke(["accounts", "not-a-command"])

        assert result.exit_code != 0
        assert_parsed_cleanly(result, caught)
        assert "Traceback" not in result.output

    def test_unknown_option_is_a_usage_error(self) -> None:
        result, caught = invoke(["accounts", "list", "--not-an-option"])

        assert result.exit_code != 0
        assert_parsed_cleanly(result, caught)
        assert "Traceback" not in result.output

    def test_missing_required_argument_is_a_usage_error(self) -> None:
        # `transactions update` requires a transaction ID argument.
        result, caught = invoke(["transactions", "update"])

        assert result.exit_code != 0
        assert_parsed_cleanly(result, caught)
        assert "Traceback" not in result.output


class TestMutationOutputSelection:
    """Mutation output selections are validated before any remote mutation."""

    def test_quiet_is_rejected_on_mutation_before_mutation(self) -> None:
        with patch("monarch_cli.commands.accounts.refresh_accounts") as mock_refresh:
            result, caught = invoke(["--quiet", "--allow-mutations", "accounts", "refresh"])

        assert result.exit_code == 2, result.output
        assert_parsed_cleanly(result, caught)
        combined = result.output + (result.stderr or "")
        assert "INVALID_INPUT" in combined
        assert "--quiet" in combined
        mock_refresh.assert_not_called()

    def test_json_is_accepted_on_mutation(self) -> None:
        outcome = {
            "schema_version": "mutation-outcome.v1",
            "operation": "accounts.refresh",
            "status": "succeeded",
            "summary": {"total": 1, "succeeded": 1, "failed": 0, "ambiguous": 0},
            "items": [
                {
                    "entity": "account",
                    "id": "acc_1",
                    "status": "succeeded",
                    "result": {},
                    "error": None,
                }
            ],
            "verification": None,
        }
        with patch("monarch_cli.commands.accounts.refresh_accounts", return_value=outcome):
            result, caught = invoke(["--json", "--allow-mutations", "accounts", "refresh"])

        assert result.exit_code == 0, result.output
        assert_parsed_cleanly(result, caught)
        data = json.loads(result.stdout)
        assert data["operation"] == "accounts.refresh"


class TestGlobalValueValidation:
    """Global option values are validated before any API call (mc-s6s6)."""

    def test_timeout_below_one_is_a_structured_error(self) -> None:
        result, caught = invoke(["--timeout", "0", "auth", "status"])

        assert result.exit_code == 2, result.output
        assert_parsed_cleanly(result, caught)
        assert json.loads(result.stderr)["code"] == "INVALID_INPUT"
