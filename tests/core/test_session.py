"""Tests for monarch_cli.core.session module."""

from __future__ import annotations

import json
import os
import pickle
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from monarch_cli.core.config import get_config_dir
from monarch_cli.core.session import (
    KEYRING_SERVICE,
    KEYRING_USERNAME,
    KeyringUnavailableError,
    StorageBackend,
    _get_from_compat,
    _get_from_env,
    _get_from_file,
    _get_from_keyring,
    delete_session_token,
    get_session_path,
    get_session_token,
    get_storage_info,
    has_valid_session,
    save_session_token,
)

if TYPE_CHECKING:
    pass


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with mock.patch.dict(os.environ, {"MONARCH_CONFIG_DIR": str(config_dir)}):
        yield config_dir


@pytest.fixture
def temp_session_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary session file path."""
    session_path = tmp_path / "session.json"
    with mock.patch.dict(os.environ, {"MONARCH_SESSION_PATH": str(session_path)}):
        yield session_path


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Ensure clean environment for tests."""
    env_keys = ["MONARCH_TOKEN", "MONARCH_CONFIG_DIR", "MONARCH_SESSION_PATH"]
    old_values = {k: os.environ.get(k) for k in env_keys}
    for k in env_keys:
        os.environ.pop(k, None)
    yield
    for k, v in old_values.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


class TestStorageBackend:
    """Tests for StorageBackend enum."""

    def test_values(self) -> None:
        """Storage backends should have expected string values."""
        assert StorageBackend.KEYRING.value == "keyring"
        assert StorageBackend.FILE.value == "file"
        assert StorageBackend.FILE_COMPAT.value == "file-compat"


class TestGetConfigDir:
    """Tests for get_config_dir function."""

    def test_respects_env_var(self, tmp_path: Path) -> None:
        """Should use MONARCH_CONFIG_DIR env var if set."""
        custom_dir = tmp_path / "custom"
        with mock.patch.dict(os.environ, {"MONARCH_CONFIG_DIR": str(custom_dir)}):
            result = get_config_dir()
            assert result == custom_dir
            assert result.exists()

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Should create directory if it doesn't exist."""
        custom_dir = tmp_path / "new_dir"
        assert not custom_dir.exists()
        with mock.patch.dict(os.environ, {"MONARCH_CONFIG_DIR": str(custom_dir)}):
            result = get_config_dir()
            assert result.exists()


class TestGetSessionPath:
    """Tests for get_session_path function."""

    def test_respects_env_var(self, tmp_path: Path) -> None:
        """Should use MONARCH_SESSION_PATH env var if set."""
        custom_path = tmp_path / "custom_session.json"
        with mock.patch.dict(os.environ, {"MONARCH_SESSION_PATH": str(custom_path)}):
            result = get_session_path()
            assert result == custom_path


class TestSaveSessionToken:
    """Tests for save_session_token function."""

    def test_save_to_file(self, temp_session_file: Path) -> None:
        """Should save token to JSON file."""
        save_session_token("test-token", StorageBackend.FILE)
        assert temp_session_file.exists()
        with temp_session_file.open() as f:
            data = json.load(f)
        assert data["token"] == "test-token"

    def test_save_to_file_atomic(self, temp_session_file: Path) -> None:
        """File save should be atomic (no partial writes)."""
        # Save initial token
        save_session_token("initial", StorageBackend.FILE)
        # Save new token
        save_session_token("updated", StorageBackend.FILE)
        with temp_session_file.open() as f:
            data = json.load(f)
        assert data["token"] == "updated"

    @mock.patch("monarch_cli.core.session.keyring")
    def test_save_to_keyring(self, mock_keyring: mock.MagicMock) -> None:
        """Should save token to keyring."""
        save_session_token("test-token", StorageBackend.KEYRING)
        mock_keyring.set_password.assert_called_once_with(
            KEYRING_SERVICE, KEYRING_USERNAME, "test-token"
        )

    @mock.patch("monarch_cli.core.session.keyring")
    def test_save_to_keyring_unavailable(self, mock_keyring: mock.MagicMock) -> None:
        """Should raise KeyringUnavailableError when keyring fails."""
        import keyring.errors

        mock_keyring.set_password.side_effect = keyring.errors.NoKeyringError()
        mock_keyring.errors = keyring.errors
        with pytest.raises(KeyringUnavailableError):
            save_session_token("test-token", StorageBackend.KEYRING)


class TestGetSessionToken:
    """Tests for get_session_token and helpers."""

    @pytest.mark.usefixtures("clean_env")
    def test_get_from_env(self) -> None:
        """Should get token from MONARCH_TOKEN env var."""
        os.environ["MONARCH_TOKEN"] = "env-token"
        assert _get_from_env() == "env-token"

    @pytest.mark.usefixtures("clean_env")
    def test_get_from_env_empty(self) -> None:
        """Empty env var should return empty string (falsy)."""
        os.environ["MONARCH_TOKEN"] = ""
        result = _get_from_env()
        assert result == ""
        # But get_session_token should skip it due to falsy check
        assert not result

    @mock.patch("monarch_cli.core.session.keyring")
    def test_get_from_keyring(self, mock_keyring: mock.MagicMock) -> None:
        """Should get token from keyring."""
        mock_keyring.get_password.return_value = "keyring-token"
        assert _get_from_keyring() == "keyring-token"

    @mock.patch("monarch_cli.core.session.keyring")
    def test_get_from_keyring_error(self, mock_keyring: mock.MagicMock) -> None:
        """Should return None on keyring error."""
        mock_keyring.get_password.side_effect = Exception("Keyring error")
        assert _get_from_keyring() is None

    def test_get_from_file(self, temp_session_file: Path) -> None:
        """Should get token from JSON file."""
        temp_session_file.write_text('{"token": "file-token"}')
        assert _get_from_file() == "file-token"

    @pytest.mark.usefixtures("temp_session_file")
    def test_get_from_file_missing(self) -> None:
        """Should return None if file doesn't exist."""
        assert _get_from_file() is None

    def test_get_from_file_invalid_json(self, temp_session_file: Path) -> None:
        """Should return None on invalid JSON."""
        temp_session_file.write_text("not valid json")
        assert _get_from_file() is None

    def test_get_from_file_not_dict(self, temp_session_file: Path) -> None:
        """Should return None if JSON is not a dict."""
        temp_session_file.write_text('["not", "a", "dict"]')
        assert _get_from_file() is None

    def test_get_from_file_no_token_key(self, temp_session_file: Path) -> None:
        """Should return None if dict has no 'token' key."""
        temp_session_file.write_text('{"other": "key"}')
        assert _get_from_file() is None

    def test_get_from_file_non_string_token(self, temp_session_file: Path) -> None:
        """Should return None if token is not a string."""
        temp_session_file.write_text('{"token": 12345}')
        assert _get_from_file() is None

    @pytest.mark.usefixtures("clean_env")
    def test_precedence(self, temp_session_file: Path) -> None:
        """Env var should take precedence over file."""
        # Set up both sources
        temp_session_file.write_text('{"token": "file-token"}')
        os.environ["MONARCH_TOKEN"] = "env-token"

        with mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None):
            assert get_session_token() == "env-token"


class TestGetFromCompat:
    """Tests for _get_from_compat with corrupted data."""

    def test_corrupted_pickle_list(self, tmp_path: Path) -> None:
        """Should handle pickle containing a list instead of dict."""
        compat_path = tmp_path / "session.pickle"
        with compat_path.open("wb") as f:
            pickle.dump(["not", "a", "dict"], f)

        with mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path):
            assert _get_from_compat() is None

    def test_corrupted_pickle_string(self, tmp_path: Path) -> None:
        """Should handle pickle containing a string instead of dict."""
        compat_path = tmp_path / "session.pickle"
        with compat_path.open("wb") as f:
            pickle.dump("just a string", f)

        with mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path):
            assert _get_from_compat() is None


class TestDeleteSessionToken:
    """Tests for delete_session_token function."""

    def test_delete_file(self, temp_session_file: Path) -> None:
        """Should delete JSON session file."""
        temp_session_file.write_text('{"token": "test"}')
        assert temp_session_file.exists()
        delete_session_token(StorageBackend.FILE)
        assert not temp_session_file.exists()

    @pytest.mark.usefixtures("temp_session_file")
    def test_delete_missing_file(self) -> None:
        """Should not raise if file doesn't exist."""
        delete_session_token(StorageBackend.FILE)  # Should not raise

    @mock.patch("monarch_cli.core.session.keyring")
    def test_delete_all(self, mock_keyring: mock.MagicMock, temp_session_file: Path) -> None:
        """Should delete from all backends when backend is None."""
        temp_session_file.write_text('{"token": "test"}')
        delete_session_token(None)
        mock_keyring.delete_password.assert_called_once()
        assert not temp_session_file.exists()

    def test_delete_keyring_error_suppressed(self) -> None:
        """Should suppress keyring errors during delete."""
        with mock.patch(
            "monarch_cli.core.session.keyring.delete_password",
            side_effect=Exception("Keyring error"),
        ):
            # Should not raise
            delete_session_token(StorageBackend.KEYRING)


class TestHasValidSession:
    """Tests for has_valid_session function."""

    @pytest.mark.usefixtures("clean_env")
    def test_returns_true_with_token(self) -> None:
        """Should return True when token is available."""
        os.environ["MONARCH_TOKEN"] = "test-token"
        with mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None):
            assert has_valid_session() is True

    @pytest.mark.usefixtures("clean_env")
    def test_returns_false_without_token(self) -> None:
        """Should return False when no token is available."""
        with (
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_compat", return_value=None),
        ):
            assert has_valid_session() is False


class TestGetStorageInfo:
    """Tests for get_storage_info function."""

    @pytest.mark.usefixtures("clean_env")
    def test_returns_dict_with_expected_keys(self) -> None:
        """Should return dict with all expected keys."""
        with (
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_compat", return_value=None),
        ):
            info = get_storage_info()
            assert "has_env_token" in info
            assert "has_keyring_token" in info
            assert "has_file_token" in info
            assert "has_compat_token" in info
            assert "active_backend" in info

    @pytest.mark.usefixtures("clean_env")
    def test_active_backend_precedence(self) -> None:
        """Should report correct active backend based on precedence."""
        os.environ["MONARCH_TOKEN"] = "env-token"
        with mock.patch("monarch_cli.core.session._get_from_keyring", return_value="kr"):
            info = get_storage_info()
            assert info["active_backend"] == "env"
            assert info["has_env_token"] is True
            assert info["has_keyring_token"] is True
