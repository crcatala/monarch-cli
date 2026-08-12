"""Agent-ergonomics regression tests for global CLI behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from monarch_cli.core.config import reset_config
from monarch_cli.main import app
from monarch_cli.output import set_default_format
from monarch_cli.output.plain import reset_color_state

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_cli_state() -> None:
    reset_config()
    set_default_format(None)
    reset_color_state()


def test_global_json_auth_status_emits_json() -> None:
    mock_info = {
        "has_env_token": False,
        "has_keyring_token": False,
        "has_file_token": False,
        "has_compat_token": False,
        "active_backend": None,
    }

    with mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info):
        result = runner.invoke(app, ["--json", "auth", "status"])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["authenticated"] is False


def test_json_auth_ping_error_emits_json_on_stdout() -> None:
    with mock.patch(
        "monarch_cli.commands.auth.get_authenticated_client",
        side_effect=RuntimeError("missing token"),
    ):
        result = runner.invoke(app, ["auth", "ping", "--json"])

    assert result.exit_code == 1
    assert result.stderr == ""
    error = json.loads(result.stdout)
    assert error["error"] is True
    assert error["code"] == "UNKNOWN"
    assert "missing token" in error["message"]


def test_non_interactive_login_fails_before_prompt() -> None:
    result = runner.invoke(app, ["--non-interactive", "auth", "login"])

    assert result.exit_code == 4
    assert "INPUT_NEEDED" in result.stderr
    assert "Cannot prompt for Email in non-interactive mode" in result.stderr


def test_usage_errors_exit_2_and_suggest_command() -> None:
    result = runner.invoke(app, ["accunts"])

    assert result.exit_code == 2
    assert "Did you mean 'accounts'?" in result.stderr


def test_corrupt_config_file_is_backed_up(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
    config_path = tmp_path / "config.toml"
    config_path.write_text("not = [valid")

    with mock.patch("monarch_cli.commands.auth.get_storage_info") as mock_storage:
        mock_storage.return_value = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_compat_token": False,
            "active_backend": None,
        }
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    backups = list(tmp_path.glob("config.toml.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "not = [valid"
    assert "Backed up corrupt config file" in result.stderr


def test_corrupt_session_file_is_backed_up(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MONARCH_SESSION_PATH", str(tmp_path / "session.json"))
    monkeypatch.delenv("MONARCH_TOKEN", raising=False)
    session_path = tmp_path / "session.json"
    session_path.write_text("not json")

    with (
        mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
        mock.patch("monarch_cli.core.session._get_from_compat", return_value=None),
    ):
        result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 0
    backups = list(tmp_path.glob("session.json.corrupt.*"))
    assert len(backups) == 1
    assert json.loads(result.stdout)["authenticated"] is False
    assert "Backed up corrupt session file" in result.stderr


def test_no_color_help_has_no_ansi(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    result = runner.invoke(app, ["--help"], color=True)

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert "Exit codes:" in result.stdout


def test_ci_env_sets_non_interactive(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")

    result = runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 4
    assert "INPUT_NEEDED" in result.stderr


def test_non_interactive_env_var_sets_non_interactive(monkeypatch) -> None:
    monkeypatch.setenv("MONARCH_NON_INTERACTIVE", "1")

    result = runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 4
    assert "INPUT_NEEDED" in result.stderr
