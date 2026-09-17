"""Non-interactive prompt policy tests (mc-2btg).

Pin the shared prompt policy: a single guard fails promptly with a stable
exit code before any input is read, driven by the global flag plus the
automation-friendly config sources, while never bypassing mutation
authorization or destructive confirmation.
"""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from monarch_cli.core.config import reset_config
from monarch_cli.core.operations import (
    reset_mutation_authorization,
    set_mutation_authorized,
)
from monarch_cli.core.prompting import (
    PROMPT_BLOCKED_EXIT_CODE,
    PromptBlockedError,
    confirm_action,
    non_interactive,
    prompt_secret,
    prompt_text,
    require_prompt_allowed,
    reset_non_interactive,
    resolve_non_interactive,
    set_non_interactive,
)
from monarch_cli.main import app

runner = CliRunner()

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolate config state and reset policy globals between tests."""
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MONARCH_TOKEN", raising=False)
    monkeypatch.delenv("MONARCH_NON_INTERACTIVE", raising=False)
    reset_mutation_authorization()
    reset_non_interactive()
    reset_config()
    yield
    reset_mutation_authorization()
    reset_non_interactive()
    reset_config()


def _refusing_input(*_args, **_kwargs):
    """Simulate an input read: must never be reached when blocked."""
    raise AssertionError("input was read despite non-interactive mode")


# --- Unit: shared guard -----------------------------------------------------


class TestPromptGuard:
    """The guard fails before any input read."""

    def test_disabled_by_default_allows_prompting(self) -> None:
        assert non_interactive() is False
        with patch("monarch_cli.core.prompting.typer.prompt", return_value="user@x.com") as p:
            assert (
                prompt_text("Email", missing_input="email", remedy="run interactively")
                == "user@x.com"
            )
        p.assert_called_once()

    def test_blocked_before_prompt_read(self) -> None:
        set_non_interactive(True)
        with (
            pytest.raises(PromptBlockedError) as excinfo,
            patch("monarch_cli.core.prompting.typer.prompt", _refusing_input),
        ):
            prompt_text("Email", missing_input="email", remedy="run interactively")
        error = excinfo.value
        assert error.exit_code == PROMPT_BLOCKED_EXIT_CODE
        assert error.code.value == "PROMPT_BLOCKED"
        assert error.details["missing_input"] == "email"
        assert error.details["remedy"] == "run interactively"

    def test_blocked_before_secret_read(self) -> None:
        set_non_interactive(True)
        with (
            pytest.raises(PromptBlockedError),
            patch("monarch_cli.core.prompting.getpass.getpass", _refusing_input),
        ):
            prompt_secret("Password: ", missing_input="password", remedy="run interactively")

    def test_blocked_before_confirmation_read(self) -> None:
        set_non_interactive(True)
        with (
            pytest.raises(PromptBlockedError) as excinfo,
            patch("monarch_cli.core.prompting.typer.confirm", _refusing_input),
        ):
            confirm_action("Delete?", missing_input="destructive confirmation", remedy="pass --yes")
        assert excinfo.value.details["missing_input"] == "destructive confirmation"

    def test_confirmation_not_auto_answered_even_when_mutations_authorized(self) -> None:
        # Non-interactive mode controls prompting, not authorization: even a
        # fully authorized invocation may not auto-answer a confirmation.
        set_mutation_authorized(True)
        set_non_interactive(True)
        with (
            pytest.raises(PromptBlockedError),
            patch("monarch_cli.core.prompting.typer.confirm", _refusing_input),
        ):
            confirm_action("Delete?", missing_input="destructive confirmation", remedy="pass --yes")

    def test_confirmation_allowed_interactively(self) -> None:
        set_mutation_authorized(True)
        with patch("monarch_cli.core.prompting.typer.confirm", return_value=True) as c:
            assert confirm_action("Delete?", missing_input="x", remedy="y") is True
        c.assert_called_once()

    def test_require_prompt_allowed_raises_with_operation(self) -> None:
        set_non_interactive(True)
        with pytest.raises(PromptBlockedError) as excinfo:
            require_prompt_allowed(
                missing_input="MFA code", remedy="run interactively", operation="auth login"
            )
        assert excinfo.value.details["operation"] == "auth login"

    def test_structured_error_shape_is_json_serializable(self) -> None:
        error = PromptBlockedError("email", "run interactively", "auth login")
        payload = error.to_dict()
        assert payload["error"] is True
        assert payload["code"] == "PROMPT_BLOCKED"
        assert "email" in payload["message"]
        assert payload["details"]["remedy"] == "run interactively"


# --- Unit: policy resolution -------------------------------------------------


class TestPolicyResolution:
    """Flag OR config (env var / config file) drives the shared policy."""

    def test_flag_enables_unconditionally(self) -> None:
        assert resolve_non_interactive(True) is True
        assert resolve_non_interactive(False) is False

    def test_env_var_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONARCH_NON_INTERACTIVE", "1")
        assert resolve_non_interactive(False) is True

    def test_env_var_false_values_do_not_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONARCH_NON_INTERACTIVE", "0")
        assert resolve_non_interactive(False) is False

    def test_config_file_enables(self, tmp_path) -> None:
        (tmp_path / "config.toml").write_text("non_interactive = true\n")
        assert resolve_non_interactive(False) is True

    def test_defaults_to_disabled(self) -> None:
        assert resolve_non_interactive(False) is False


# --- Integration: CLI behavior ----------------------------------------------


class TestCliNonInteractive:
    """End-to-end behavior through the real CLI app (no network)."""

    def test_login_blocked_before_any_input_or_output(self) -> None:
        result = runner.invoke(app, ["--non-interactive", "auth", "login"], catch_exceptions=False)
        assert result.exit_code == PROMPT_BLOCKED_EXIT_CODE, result.output
        # No banner or other prose on stdout.
        assert result.stdout == "", result.stdout
        stderr = result.stderr or ""
        assert ANSI_ESCAPE_RE.search(stderr) is None, stderr
        payload = json.loads(stderr)
        assert payload["error"] is True
        assert payload["code"] == "PROMPT_BLOCKED"
        assert payload["details"]["missing_input"] == "email and password"
        assert "MONARCH_TOKEN" in payload["details"]["remedy"]

    def test_login_blocked_does_not_read_credentials(self) -> None:
        with (
            patch("monarch_cli.core.prompting.typer.prompt", _refusing_input),
            patch("monarch_cli.core.prompting.getpass.getpass", _refusing_input),
        ):
            result = runner.invoke(app, ["--non-interactive", "auth", "login"])
        assert result.exit_code == PROMPT_BLOCKED_EXIT_CODE, result.output

    def test_env_var_enables_non_interactive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONARCH_NON_INTERACTIVE", "true")
        result = runner.invoke(app, ["auth", "login"])
        assert result.exit_code == PROMPT_BLOCKED_EXIT_CODE, result.output

    def test_config_file_enables_non_interactive(self, tmp_path) -> None:
        (tmp_path / "config.toml").write_text("non_interactive = true\n")
        result = runner.invoke(app, ["auth", "login"])
        assert result.exit_code == PROMPT_BLOCKED_EXIT_CODE, result.output

    def test_flag_combines_with_disabled_config(self, tmp_path) -> None:
        (tmp_path / "config.toml").write_text("non_interactive = false\n")
        result = runner.invoke(app, ["--non-interactive", "auth", "login"])
        assert result.exit_code == PROMPT_BLOCKED_EXIT_CODE, result.output

    def test_interactive_login_behavior_unchanged(self) -> None:
        """Without the mode, prompts still happen and login proceeds."""
        with (
            patch("monarch_cli.core.prompting.typer.prompt", return_value="user@x.com") as p,
            patch("monarch_cli.core.prompting.getpass.getpass", return_value="pw"),
            patch("monarch_cli.commands.auth.MonarchMoney") as mm_cls,
        ):
            mm_cls.return_value.login.side_effect = RuntimeError("offline")
            result = runner.invoke(app, ["auth", "login"])
        # Prompts were reached (interactive behavior preserved); login failed
        # for the simulated network reason, not because of prompt policy.
        p.assert_called_once()
        assert result.exit_code == 1
        assert "Login failed" in (result.stderr or "")

    def test_non_interactive_does_not_bypass_mutation_authorization(self) -> None:
        result = runner.invoke(
            app,
            ["--non-interactive", "transactions", "update", "TXN1", "--amount", "1.0"],
        )
        assert result.exit_code == 3, result.output
        stderr = result.stderr or ""
        assert "MUTATION_BLOCKED" in stderr
        assert "PROMPT_BLOCKED" not in stderr

    def test_non_interactive_with_authorization_still_requires_confirmation(self) -> None:
        # Even with --allow-mutations, non-interactive mode cannot satisfy a
        # destructive confirmation; the confirm guard still refuses input.
        set_mutation_authorized(True)
        set_non_interactive(True)
        with (
            pytest.raises(PromptBlockedError),
            patch("monarch_cli.core.prompting.typer.confirm", _refusing_input),
        ):
            confirm_action(
                "Delete transaction?",
                missing_input="destructive confirmation",
                remedy="re-run interactively",
                operation="transactions delete",
            )

    def test_explicit_stdin_redirect_still_works(self) -> None:
        """--stdin is deliberate input redirection, not a prompt: it must
        remain usable under non-interactive mode."""
        result = runner.invoke(
            app,
            [
                "--non-interactive",
                "transactions",
                "batch-update",
                "--stdin",
                "--notes",
                "Q1",
                "--dry-run",
            ],
            input="TXN1\n\nTXN2\n",
        )
        assert result.exit_code == 0, result.output
        assert '"transaction_count": 2' in result.stdout

    def test_global_option_registered_before_command_path(self) -> None:
        result = runner.invoke(app, ["--non-interactive", "--version"])
        assert result.exit_code == 0, result.output

    def test_policy_state_does_not_persist_between_invocations(self) -> None:
        first = runner.invoke(app, ["--non-interactive", "auth", "login"])
        assert first.exit_code == PROMPT_BLOCKED_EXIT_CODE
        assert non_interactive() is True
        # A subsequent invocation without the flag is interactive again.
        with (
            patch("monarch_cli.core.prompting.typer.prompt", return_value="user@x.com"),
            patch("monarch_cli.core.prompting.getpass.getpass", return_value="pw"),
            patch("monarch_cli.commands.auth.MonarchMoney") as mm_cls,
        ):
            mm_cls.return_value.login.side_effect = RuntimeError("offline")
            second = runner.invoke(app, ["auth", "login"])
        assert second.exit_code == 1
        assert "Login failed" in (second.stderr or "")
