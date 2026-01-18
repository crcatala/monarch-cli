"""Tests for auth commands."""

from __future__ import annotations

import json
from unittest import mock

from typer.testing import CliRunner

from monarch_cli.core.session import StorageBackend
from monarch_cli.main import app

runner = CliRunner()


class TestAuthStatus:
    """Tests for 'monarch auth status' command."""

    def test_status_human_readable_when_authenticated(self) -> None:
        """Should show human-readable output by default when authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": True,
            "has_file_token": False,
            "has_compat_token": False,
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

    def test_status_human_readable_when_not_authenticated(self) -> None:
        """Should show human-readable prompt when not authenticated."""
        mock_info = {
            "has_env_token": False,
            "has_keyring_token": False,
            "has_file_token": False,
            "has_compat_token": False,
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
            "has_compat_token": False,
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
            "has_compat_token": False,
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
            "has_compat_token": False,
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

    def test_logout_file_compat_backend(self) -> None:
        """Should clear only file-compat backend when specified."""
        with (
            mock.patch("monarch_cli.commands.auth.delete_session_token") as mock_delete,
            mock.patch("monarch_cli.commands.auth.reset_client"),
        ):
            result = runner.invoke(app, ["auth", "logout", "-s", "file-compat"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with(StorageBackend.FILE_COMPAT)

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
                "monarch_cli.commands.auth.run_async",
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
                "monarch_cli.commands.auth.run_async",
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
                "monarch_cli.commands.auth.run_async",
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
                "monarch_cli.commands.auth.run_async",
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
            "has_compat_token": False,
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
            "has_compat_token": False,
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
            "has_compat_token": False,
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
            "has_compat_token": False,
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
                "monarch_cli.commands.auth.run_async",
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
            "has_compat_token": False,
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
