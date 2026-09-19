"""Tests for monarch_cli.core.session module."""

from __future__ import annotations

import json
import os
import pickle
import stat
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
    _get_from_env,
    _get_from_file,
    _get_from_keyring,
    delete_session_token,
    get_session_path,
    get_session_token,
    get_storage_info,
    has_valid_session,
    legacy_artifact_exists,
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

    def test_no_file_compat_member(self) -> None:
        """The legacy file-compat backend must not exist."""
        assert "FILE_COMPAT" not in StorageBackend.__members__
        assert "file-compat" not in [b.value for b in StorageBackend]


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

    @pytest.mark.skipif(os.name != "posix", reason="POSIX file mode check")
    def test_save_to_file_mode_0600_posix(self, temp_session_file: Path) -> None:
        """Atomic JSON writes must produce mode 0600 on POSIX."""
        save_session_token("test-token", StorageBackend.FILE)
        mode = stat.S_IMODE(temp_session_file.stat().st_mode)
        assert mode == 0o600

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


class _HostilePickle:
    """Object that records execution if its pickle payload is deserialized."""

    def __reduce__(self) -> tuple[object, tuple[()]]:
        return _hostile_mark, ()


HOSTILE_SENTINEL: list[str] = []


def _hostile_mark() -> str:
    """Called only if the hostile pickle payload is actually unpickled."""
    HOSTILE_SENTINEL.append("executed")
    return "hostile-code-ran"


def _write_hostile_pickle(path: Path) -> None:
    """Write a pickle that would execute code if deserialized."""
    path.write_bytes(pickle.dumps(_HostilePickle()))


class TestLegacyArtifact:
    """Legacy pickle artifact is detected by metadata only, never read."""

    @pytest.fixture(autouse=True)
    def _reset_sentinel(self) -> None:
        HOSTILE_SENTINEL.clear()

    def test_legacy_artifact_exists_true(self, tmp_path: Path) -> None:
        """Should report presence when the artifact file exists."""
        compat_path = tmp_path / "mm_session.pickle"
        compat_path.write_bytes(b"anything")
        with mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path):
            assert legacy_artifact_exists() is True

    def test_legacy_artifact_exists_false(self, tmp_path: Path) -> None:
        """Should report absence when the artifact file does not exist."""
        compat_path = tmp_path / "mm_session.pickle"
        with mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path):
            assert legacy_artifact_exists() is False

    @pytest.mark.usefixtures("clean_env")
    def test_hostile_pickle_not_deserialized_by_get_session_token(self, tmp_path: Path) -> None:
        """get_session_token must never execute a hostile legacy pickle."""
        compat_path = tmp_path / "mm_session.pickle"
        _write_hostile_pickle(compat_path)
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
        ):
            assert get_session_token() is None
            assert legacy_artifact_exists() is True
        assert HOSTILE_SENTINEL == []

    @pytest.mark.usefixtures("clean_env")
    def test_hostile_pickle_not_deserialized_by_storage_info(self, tmp_path: Path) -> None:
        """get_storage_info must use metadata only, never deserialize."""
        compat_path = tmp_path / "mm_session.pickle"
        _write_hostile_pickle(compat_path)
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
        ):
            info = get_storage_info()
        assert info["has_legacy_artifact"] is True
        assert info["active_backend"] is None
        assert HOSTILE_SENTINEL == []

    @pytest.mark.usefixtures("clean_env")
    def test_hostile_pickle_not_deserialized_by_has_valid_session(self, tmp_path: Path) -> None:
        """has_valid_session must not deserialize the legacy artifact."""
        compat_path = tmp_path / "mm_session.pickle"
        _write_hostile_pickle(compat_path)
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
        ):
            assert has_valid_session() is False
        assert HOSTILE_SENTINEL == []

    def test_no_pickle_import_in_session_module(self) -> None:
        """The session module must not import pickle at all."""
        import sys

        session_module = sys.modules["monarch_cli.core.session"]
        assert not hasattr(session_module, "pickle")
        assert "pickle" not in session_module.__dict__

    def test_storage_info_documented_keys(self, tmp_path: Path) -> None:
        """get_storage_info should report legacy artifact presence, not tokens."""
        compat_path = tmp_path / "mm_session.pickle"
        compat_path.write_bytes(b"\x80\x04not really a pickle")
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
        ):
            info = get_storage_info()
        assert "has_compat_token" not in info
        assert info["has_legacy_artifact"] is True
        assert info["active_backend"] is None


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

    def test_delete_all_never_touches_legacy_artifact(self, tmp_path: Path) -> None:
        """Logout must not implicitly delete or quarantine the legacy artifact."""
        compat_path = tmp_path / "mm_session.pickle"
        compat_path.write_bytes(b"legacy pickle bytes")
        with (
            mock.patch("monarch_cli.core.session.keyring"),
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch(
                "monarch_cli.core.session.get_session_path", return_value=tmp_path / "s.json"
            ),
        ):
            delete_session_token(None)
        assert compat_path.exists()

    def test_delete_file_backend_does_not_touch_legacy_artifact(self, tmp_path: Path) -> None:
        """Deleting the file backend must not remove the legacy artifact."""
        compat_path = tmp_path / "mm_session.pickle"
        compat_path.write_bytes(b"legacy pickle bytes")
        with mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path):
            delete_session_token(StorageBackend.FILE)
        assert compat_path.exists()

    def test_delete_ignores_hostile_legacy_artifact(self, tmp_path: Path) -> None:
        """Logout must operate safely with a hostile legacy artifact present."""
        compat_path = tmp_path / "mm_session.pickle"
        compat_path.write_bytes(b"\x80\x04\x95hostile-garbage")
        with (
            mock.patch("monarch_cli.core.session.keyring"),
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch(
                "monarch_cli.core.session.get_session_path", return_value=tmp_path / "s.json"
            ),
        ):
            # Should not raise and should not deserialize the artifact.
            delete_session_token(None)
        assert compat_path.exists()

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
        ):
            info = get_storage_info()
            assert "has_env_token" in info
            assert "has_keyring_token" in info
            assert "has_file_token" in info
            assert "has_legacy_artifact" in info
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

    @pytest.mark.usefixtures("clean_env")
    def test_legacy_artifact_is_not_active_backend(self, tmp_path: Path) -> None:
        """A legacy artifact must never appear as an active credential."""
        compat_path = tmp_path / "mm_session.pickle"
        compat_path.write_bytes(b"legacy pickle bytes")
        with (
            mock.patch("monarch_cli.core.session.COMPAT_SESSION_PATH", compat_path),
            mock.patch("monarch_cli.core.session._get_from_keyring", return_value=None),
            mock.patch("monarch_cli.core.session._get_from_file", return_value=None),
        ):
            info = get_storage_info()
        assert info["has_legacy_artifact"] is True
        assert info["active_backend"] is None


def test_keyring_unavailable_message_recommends_storage_file() -> None:
    """Keyring guidance must name the real --storage=file option (mc-s6s6)."""
    from monarch_cli.core.session import KeyringUnavailableError

    error = KeyringUnavailableError()
    assert "--storage=file" in error.message
    assert "--backend=file" not in error.message
