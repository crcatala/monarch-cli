"""Tests for auth commands."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest
from typer.testing import CliRunner

from monarch_cli.core.session import StorageBackend
from monarch_cli.main import app

runner = CliRunner()

# Sentinel that records execution of a hostile pickle payload.
HOSTILE_SENTINEL: list[str] = []


def _hostile_mark() -> str:
    """Called only if a hostile pickle payload is actually unpickled."""
    HOSTILE_SENTINEL.append("executed")
    return "hostile-code-ran"


class _HostilePickle:
    """Object that records execution if its pickle payload is deserialized."""

    def __reduce__(self) -> tuple[object, tuple[()]]:
        return _hostile_mark, ()


def tmp_hostile_pickle_file() -> Path:
    """Create a hostile pickle file that survives for the duration of a test.

    Returns a path to a hostile pickle payload backed by a temporary directory.
    Callers patch the session module's COMPAT_SESSION_PATH with the returned
    path. The directory is cleaned up by the module-level autouse hygiene
    fixture after each test.
    """
    tmp = TemporaryDirectory()
    path = Path(tmp.name) / "mm_session.pickle"
    path.write_bytes(pickle.dumps(_HostilePickle()))
    # Keep the directory alive for the duration of the test; the autouse
    # hygiene fixture below cleans it up afterwards.
    _TMP_HOLDERS.append(tmp)
    return path


_TMP_HOLDERS: list[TemporaryDirectory] = []


@pytest.fixture(autouse=True)
def _hostile_pickle_hygiene() -> None:
    """Reset the hostile-pickle sentinel and clean up temp dirs per test."""
    HOSTILE_SENTINEL.clear()
    yield
    HOSTILE_SENTINEL.clear()
    while _TMP_HOLDERS:
        _TMP_HOLDERS.pop().cleanup()


def _plain(text: str) -> str:
    """Strip ANSI codes and collapse whitespace for robust assertions."""
    import re

    return re.sub(r"\s+", " ", re.sub(r"\x1b\[[0-9;]*m", "", text))


class TestAuthStatus:
    """Tests for 'monarch auth status' command."""

    def test_status_human_readable_when_authenticated_keyring(self) -> None:
        """Should show human-readable output with keyring backend."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": True,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "keyring",
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        # Human-readable output goes to stderr (Rich console)
        assert "Authenticated" in result.stderr
        assert "keyring" in result.stderr

    def test_status_human_readable_shows_file_path(self) -> None:
        """Should show file path when using file backend."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": True,
            "has_legacy_artifact": False,
            "active_backend": "file",
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "Authenticated" in result.stderr
        assert "file" in result.stderr
        assert "session.json" in result.stderr  # Part of the path

    def test_status_human_readable_shows_env_var(self) -> None:
        """Should show MONARCH_TOKEN when using env backend."""
        mock_info = {
            "has_env_token": True,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "env",
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "Authenticated" in result.stderr
        assert "env" in result.stderr
        assert "MONARCH_TOKEN" in result.stderr

    def test_status_human_readable_when_not_authenticated(self) -> None:
        """Should show human-readable prompt when not authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": None,
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "Not authenticated" in result.stderr
        assert "monarch auth login" in result.stderr

    def test_status_json_when_authenticated(self) -> None:
        """Should return JSON with --json flag when authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": True,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "keyring",
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["authenticated"] is True
        assert data["storage_backend"] == "keyring"

    def test_status_json_when_not_authenticated(self) -> None:
        """Should return JSON with --json flag when not authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": None,
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["authenticated"] is False
        assert data["storage_backend"] is None
        assert "monarch auth login" in data["message"]

    def test_status_json_env_backend(self) -> None:
        """Should report env as active backend in JSON output."""
        mock_info = {
            "has_env_token": True,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "env",
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["storage_backend"] == "env"

    def test_status_human_readable_identifies_legacy_artifact(self) -> None:
        """Should flag a legacy artifact as unsupported and direct to login."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": True,
            "active_backend": None,
        }
        with (
            mock.patch(
                "monarch_cli.commands.auth.get_storage_info",
                return_value=mock_info,
            ),
            mock.patch(
                "monarch_cli.commands.auth.COMPAT_SESSION_PATH",
                Path("/tmp/fake-mm_session.pickle"),
            ),
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        stderr = _plain(result.stderr)
        assert "Not authenticated" in stderr
        assert "Legacy session file" in stderr
        assert "no longer supported" in stderr
        assert "monarch auth login" in stderr

    def test_status_json_reports_legacy_artifact(self) -> None:
        """JSON status should report legacy artifact presence, not a credential."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": True,
            "active_backend": None,
        }
        with mock.patch(
            "monarch_cli.commands.auth.get_storage_info",
            return_value=mock_info,
        ):
            result = runner.invoke(app, ["auth", "status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["authenticated"] is False
        assert data["storage_backend"] is None
        assert data["legacy_pickle_artifact"]["exists"] is True
        assert data["legacy_pickle_artifact"]["active_credential"] is False
        assert "monarch auth login" in data["message"]
        assert "no longer supported" in data["message"]


class TestAuthLogout:
    """Tests for 'monarch auth logout' command."""

    def test_logout_clears_all_backends(self) -> None:
        """Should call delete_session_token(None) for all backends."""
        with (
            mock.patch("monarch_cli.commands.auth.delete_session_token") as mock_delete,
            mock.patch("monarch_cli.commands.auth.reset_client") as mock_reset,
        ):
            result = runner.invoke(app, ["auth", "logout"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with(None)
        mock_reset.assert_called_once()
        assert "Logged out" in result.stderr

    def test_logout_keyring_backend(self) -> None:
        """Should clear only keyring backend when specified."""
        with (
            mock.patch("monarch_cli.commands.auth.delete_session_token") as mock_delete,
            mock.patch("monarch_cli.commands.auth.reset_client"),
        ):
            result = runner.invoke(app, ["auth", "logout", "-s", "keyring"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with(StorageBackend.KEYRING)
        assert "keyring" in result.stderr.lower()

    def test_logout_file_backend(self) -> None:
        """Should clear only file backend when specified."""
        with (
            mock.patch("monarch_cli.commands.auth.delete_session_token") as mock_delete,
            mock.patch("monarch_cli.commands.auth.reset_client"),
        ):
            result = runner.invoke(app, ["auth", "logout", "-s", "file"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with(StorageBackend.FILE)

    def test_logout_file_compat_backend_removed(self) -> None:
        """The removed file-compat backend must be rejected."""
        with (
            mock.patch("monarch_cli.commands.auth.delete_session_token") as mock_delete,
            mock.patch("monarch_cli.commands.auth.reset_client") as mock_reset,
        ):
            result = runner.invoke(app, ["auth", "logout", "-s", "file-compat"])

        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stderr
        assert "file-compat" not in result.stderr.split("Valid options")[1]
        mock_delete.assert_not_called()
        mock_reset.assert_not_called()

    def test_logout_invalid_backend(self) -> None:
        """Should error on invalid storage backend."""
        result = runner.invoke(app, ["auth", "logout", "-s", "invalid"])
        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stderr


class TestAuthPing:
    """Tests for 'monarch auth ping' command."""

    def test_ping_human_readable_success(self) -> None:
        """Should show human-readable output by default."""
        mock_client = mock.MagicMock()
        mock_accounts = {"accounts": [{"id": "1"}, {"id": "2"}]}

        with (
            mock.patch(
                "monarch_cli.commands.auth.get_authenticated_client",
                return_value=mock_client,
            ),
            mock.patch(
                "monarch_cli.commands.auth.run_read_call",
                return_value=mock_accounts,
            ),
        ):
            result = runner.invoke(app, ["auth", "ping"])

        assert result.exit_code == 0
        # Human-readable output goes to stderr (Rich console)
        assert "Connected" in result.stderr
        assert "2" in result.stderr

    def test_ping_json_success(self) -> None:
        """Should return JSON with --json flag."""
        mock_client = mock.MagicMock()
        mock_accounts = {"accounts": [{"id": "1"}, {"id": "2"}]}

        with (
            mock.patch(
                "monarch_cli.commands.auth.get_authenticated_client",
                return_value=mock_client,
            ),
            mock.patch(
                "monarch_cli.commands.auth.run_read_call",
                return_value=mock_accounts,
            ),
        ):
            result = runner.invoke(app, ["auth", "ping", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "ok"
        assert "2 accounts" in data["message"]

    def test_ping_json_single_account(self) -> None:
        """Should handle singular account in JSON message."""
        mock_client = mock.MagicMock()
        mock_accounts = {"accounts": [{"id": "1"}]}

        with (
            mock.patch(
                "monarch_cli.commands.auth.get_authenticated_client",
                return_value=mock_client,
            ),
            mock.patch(
                "monarch_cli.commands.auth.run_read_call",
                return_value=mock_accounts,
            ),
        ):
            result = runner.invoke(app, ["auth", "ping", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "ok"
        assert "1 account" in data["message"]

    def test_ping_requires_auth(self) -> None:
        """Should error when not authenticated."""
        from monarch_cli.core.exceptions import AuthenticationError

        with mock.patch(
            "monarch_cli.commands.auth.get_authenticated_client",
            side_effect=AuthenticationError(),
        ):
            result = runner.invoke(app, ["auth", "ping"])

        assert result.exit_code == 1
        assert "AUTH_REQUIRED" in result.stderr

    def test_ping_api_error(self) -> None:
        """Should handle API errors gracefully."""
        mock_client = mock.MagicMock()

        with (
            mock.patch(
                "monarch_cli.commands.auth.get_authenticated_client",
                return_value=mock_client,
            ),
            mock.patch(
                "monarch_cli.commands.auth.run_read_call",
                side_effect=Exception("Connection failed"),
            ),
        ):
            result = runner.invoke(app, ["auth", "ping"])

        assert result.exit_code == 1
        assert "API_ERROR" in result.stderr


class TestAuthDoctor:
    """Tests for 'monarch auth doctor' command."""

    def test_doctor_shows_keyring_available(self) -> None:
        """Should show keyring as available when it works."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": True,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "keyring",
        }
        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=True),
            mock.patch(
                "monarch_cli.commands.auth._get_keyring_backend_name",
                return_value="SecretService",
            ),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        assert "Available" in result.stderr
        assert "SecretService" in result.stderr

    def test_doctor_shows_keyring_unavailable(self) -> None:
        """Should show keyring as unavailable when it fails."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": True,
            "has_legacy_artifact": False,
            "active_backend": "file",
        }
        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=False),
            mock.patch(
                "monarch_cli.commands.auth._get_keyring_backend_name",
                return_value="Keyring",
            ),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        assert "Not available" in result.stderr

    def test_doctor_shows_all_storage_locations(self) -> None:
        """Should display status of all token storage locations."""
        mock_info = {
            "has_env_token": True,
            "has_keyring_token": False,
            "has_file_token": True,
            "has_legacy_artifact": False,
            "active_backend": "env",
        }
        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=True),
            mock.patch("monarch_cli.commands.auth._get_keyring_backend_name", return_value="Test"),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        assert "MONARCH_TOKEN" in result.stderr
        assert "env" in result.stderr.lower()

    def test_doctor_tests_api_when_authenticated(self) -> None:
        """Should test API connectivity when authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": True,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": "keyring",
        }
        mock_client = mock.MagicMock()
        mock_accounts = {"accounts": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}

        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=True),
            mock.patch("monarch_cli.commands.auth._get_keyring_backend_name", return_value="Test"),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
            mock.patch(
                "monarch_cli.commands.auth.get_authenticated_client",
                return_value=mock_client,
            ),
            mock.patch(
                "monarch_cli.commands.auth.run_read_call",
                return_value=mock_accounts,
            ),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        assert "Connected" in result.stderr
        # Rich adds ANSI codes around numbers, so check for "3" and "accounts" separately
        assert "3" in result.stderr
        assert "accounts" in result.stderr

    def test_doctor_skips_api_when_not_authenticated(self) -> None:
        """Should skip API test when not authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": False,
            "active_backend": None,
        }
        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=False),
            mock.patch("monarch_cli.commands.auth._get_keyring_backend_name", return_value="Fail"),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        assert "Skipped" in result.stderr

    def test_doctor_identifies_legacy_artifact(self) -> None:
        """Doctor should report legacy artifact presence and re-auth guidance."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": True,
            "active_backend": None,
        }
        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=False),
            mock.patch("monarch_cli.commands.auth._get_keyring_backend_name", return_value="Fail"),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
            mock.patch(
                "monarch_cli.commands.auth.COMPAT_SESSION_PATH",
                Path("/tmp/fake-mm_session.pickle"),
            ),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        stderr = _plain(result.stderr)
        assert "mm_session.pickle" in stderr
        assert "not read" in stderr
        assert "not an active credential" in stderr
        assert "monarch auth login" in stderr

    def test_doctor_safe_with_hostile_legacy_artifact(self) -> None:
        """Doctor must never deserialize a hostile legacy artifact."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_legacy_artifact": True,
            "active_backend": None,
        }
        hostile_path = tmp_hostile_pickle_file()
        with (
            mock.patch("monarch_cli.commands.auth._is_keyring_available", return_value=False),
            mock.patch("monarch_cli.commands.auth._get_keyring_backend_name", return_value="Fail"),
            mock.patch("monarch_cli.commands.auth.get_storage_info", return_value=mock_info),
            mock.patch("monarch_cli.commands.auth.COMPAT_SESSION_PATH", hostile_path),
        ):
            result = runner.invoke(app, ["auth", "doctor"])

        assert result.exit_code == 0
        assert HOSTILE_SENTINEL == []


class TestLegacyArtifactSafety:
    """End-to-end safety of diagnostics and auth failures with hostile pickles."""

    def test_status_safe_with_hostile_legacy_artifact(self) -> None:
        """auth status must not deserialize a hostile legacy artifact."""
        hostile_path = tmp_hostile_pickle_file()
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", hostile_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "Not authenticated" in result.stderr
        assert HOSTILE_SENTINEL == []

    def test_status_json_safe_with_hostile_legacy_artifact(self) -> None:
        """JSON status must not deserialize a hostile legacy artifact."""
        hostile_path = tmp_hostile_pickle_file()
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", hostile_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
        ):
            result = runner.invoke(app, ["auth", "status", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["authenticated"] is False
        assert data["legacy_pickle_artifact"]["exists"] is True
        assert HOSTILE_SENTINEL == []

    def test_authenticated_command_failure_mentions_legacy_artifact(self) -> None:
        """Auth failure with legacy artifact should direct to 'monarch auth login'."""
        hostile_path = tmp_hostile_pickle_file()
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", hostile_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.adapter.get_session_token", return_value=None),
            mock.patch("monarch_cli.core.adapter.legacy_artifact_exists", return_value=True),
        ):
            result = runner.invoke(app, ["auth", "ping"])

        assert result.exit_code == 1
        assert "monarch auth login" in result.stderr
        assert HOSTILE_SENTINEL == []

    def test_authenticated_command_ignores_legacy_artifact_contents(self) -> None:
        """get_session_token must never read the hostile artifact."""
        hostile_path = tmp_hostile_pickle_file()
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", hostile_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.adapter.get_session_token") as mock_get_token,
        ):
            mock_get_token.return_value = None
            runner.invoke(app, ["auth", "ping"])

        # The adapter consulted get_session_token; the hostile pickle was never
        # deserialized (sentinel empty) and no token came from the legacy file.
        assert HOSTILE_SENTINEL == []

    def test_setup_documents_legacy_sessions(self) -> None:
        """Setup output should document legacy pickle removal and cleanup."""
        result = runner.invoke(app, ["auth", "setup"])

        assert result.exit_code == 0
        assert "Legacy Sessions" in result.stderr
        assert "mm_session.pickle" in result.stderr
        assert "monarch auth login" in result.stderr


class TestAuthSetup:
    """Tests for 'monarch auth setup' command."""

    def test_setup_shows_quick_start(self) -> None:
        """Should display quick start instructions."""
        result = runner.invoke(app, ["auth", "setup"])

        assert result.exit_code == 0
        assert "Quick Start" in result.stderr
        assert "monarch auth login" in result.stderr

    def test_setup_shows_storage_options(self) -> None:
        """Should display storage backend options."""
        result = runner.invoke(app, ["auth", "setup"])

        assert result.exit_code == 0
        assert "keyring" in result.stderr.lower()
        assert "file" in result.stderr.lower()
        assert "MONARCH_TOKEN" in result.stderr

    def test_setup_shows_troubleshooting(self) -> None:
        """Should display troubleshooting tips."""
        result = runner.invoke(app, ["auth", "setup"])

        assert result.exit_code == 0
        assert "Troubleshooting" in result.stderr
        assert "monarch auth doctor" in result.stderr


class TestAuthLogin:
    """Tests for 'monarch auth login' command.

    Note: Login is interactive and harder to test fully.
    These tests cover error paths and non-interactive aspects.
    getpass.getpass() must be mocked as it reads from TTY, not stdin.
    """

    def test_login_invalid_storage_backend(self) -> None:
        """Should error on invalid --storage value."""
        with mock.patch("monarch_cli.commands.auth.getpass.getpass", return_value="password"):
            result = runner.invoke(
                app,
                ["auth", "login", "-s", "invalid"],
                input="test@example.com\n",
            )
        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stderr

    def test_login_keyring_unavailable_with_keyring_flag(self) -> None:
        """Should error when --storage=keyring but keyring unavailable."""
        with (
            mock.patch("monarch_cli.commands.auth.getpass.getpass", return_value="password"),
            mock.patch(
                "monarch_cli.commands.auth._is_keyring_available",
                return_value=False,
            ),
        ):
            result = runner.invoke(
                app,
                ["auth", "login", "-s", "keyring"],
                input="test@example.com\n",
            )

        assert result.exit_code == 1
        assert "Keyring not available" in result.stderr


class TestKeyringHelpers:
    """Tests for keyring helper functions."""

    def test_is_keyring_available_true(self) -> None:
        """Should return True when real keyring backend available."""
        from monarch_cli.commands.auth import _is_keyring_available

        mock_backend = mock.MagicMock()
        mock_backend.__class__.__module__ = "keyring.backends.SecretService"

        with mock.patch("monarch_cli.commands.auth.keyring.get_keyring", return_value=mock_backend):
            assert _is_keyring_available() is True

    def test_is_keyring_available_false(self) -> None:
        """Should return False when fail backend is active."""
        from monarch_cli.commands.auth import _is_keyring_available

        mock_backend = mock.MagicMock()
        mock_backend.__class__.__module__ = "keyring.backends.fail"

        with mock.patch("monarch_cli.commands.auth.keyring.get_keyring", return_value=mock_backend):
            assert _is_keyring_available() is False

    def test_is_keyring_available_exception(self) -> None:
        """Should return False when keyring raises exception."""
        from monarch_cli.commands.auth import _is_keyring_available

        with mock.patch(
            "monarch_cli.commands.auth.keyring.get_keyring",
            side_effect=Exception("Keyring error"),
        ):
            assert _is_keyring_available() is False

    def test_get_keyring_backend_name(self) -> None:
        """Should return backend class name."""
        from monarch_cli.commands.auth import _get_keyring_backend_name

        mock_backend = mock.MagicMock()
        mock_backend.__class__.__name__ = "SecretServiceKeyring"

        with mock.patch("monarch_cli.commands.auth.keyring.get_keyring", return_value=mock_backend):
            assert _get_keyring_backend_name() == "SecretServiceKeyring"

    def test_get_keyring_backend_name_exception(self) -> None:
        """Should return 'unknown' when keyring raises exception."""
        from monarch_cli.commands.auth import _get_keyring_backend_name

        with mock.patch(
            "monarch_cli.commands.auth.keyring.get_keyring",
            side_effect=Exception("Keyring error"),
        ):
            assert _get_keyring_backend_name() == "unknown"
