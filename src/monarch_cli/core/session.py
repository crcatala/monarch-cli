"""Session management with dual-backend token storage.

Supported backends, in precedence order:
1. ``MONARCH_TOKEN`` environment variable
2. System keyring (secure, default)
3. Atomic JSON file (portable)

Legacy pickle session files (``~/.mm/mm_session.pickle``) are no longer a
credential source. Pickle deserialization can execute arbitrary code, so a
legacy file is never read, only detected as a filesystem artifact so that
diagnostics can direct the user to ``monarch auth login`` for re-auth.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import keyring
import keyring.errors

from .config import get_config_dir
from .exceptions import ErrorCode, MonarchCLIError

if TYPE_CHECKING:
    from typing import Any

# Keyring constants
KEYRING_SERVICE = "com.monarch-cli"
KEYRING_USERNAME = "monarch-token"

# Legacy pickle session artifact written by older releases (and the
# monarchmoney library). Its contents are NEVER read: presence is detected via
# filesystem metadata only so diagnostics can direct users to re-authenticate.
COMPAT_SESSION_PATH = Path.home() / ".mm" / "mm_session.pickle"


class KeyringUnavailableError(MonarchCLIError):
    """Keyring backend is not available."""

    def __init__(
        self,
        message: str = "Keyring unavailable. Use --backend=file or set MONARCH_TOKEN env var.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.AUTH_FAILED,
            details=details,
            exit_code=1,
        )


class StorageBackend(StrEnum):
    """Token storage backends in order of security preference."""

    KEYRING = "keyring"
    FILE = "file"


def get_session_path() -> Path:
    """Get the session file path, respecting MONARCH_SESSION_PATH env var.

    Returns:
        Path to session.json file.
    """
    env_path = os.environ.get("MONARCH_SESSION_PATH")
    if env_path:
        return Path(env_path)
    return get_config_dir() / "session.json"


def _set_file_permissions(fd: int) -> None:
    """Set secure file permissions (0600) on POSIX platforms.

    On POSIX, the resulting credential file has mode ``0600`` (owner
    read/write only). On Windows, ``os.fchmod`` is not applicable; the file
    inherits the default NTFS ACLs of the user's profile directory, which
    restricts access to the user and administrators. Those ACLs are not
    equivalent to POSIX mode ``0600`` and should not be described as such.

    Args:
        fd: File descriptor to set permissions on.
    """
    # os.fchmod is Unix-only; skip on Windows
    if sys.platform != "win32":
        os.fchmod(fd, 0o600)


def _save_to_keyring(token: str) -> None:
    """Save token to OS keyring.

    Raises:
        KeyringUnavailableError: If no keyring backend is available.
    """
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    except keyring.errors.NoKeyringError as e:
        raise KeyringUnavailableError(details={"original_error": str(e)}) from e
    except keyring.errors.KeyringError as e:
        raise KeyringUnavailableError(
            message=f"Keyring error: {e}. Use --backend=file or set MONARCH_TOKEN env var.",
            details={"original_error": str(e)},
        ) from e


def _save_to_file(token: str) -> None:
    """Save token to JSON file with secure atomic write.

    Uses temp file + rename for atomicity. Sets 0600 permissions
    before writing content for security (Unix only).
    """
    session_path = get_session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory for atomic rename
    fd, tmp_path = tempfile.mkstemp(dir=session_path.parent, suffix=".tmp")
    tmp_path_obj = Path(tmp_path)
    try:
        _set_file_permissions(fd)  # Set perms before writing (Unix only)
        with os.fdopen(fd, "w") as f:
            json.dump({"token": token}, f)
        os.replace(tmp_path, session_path)  # Atomic replace
    except Exception:
        if tmp_path_obj.exists():
            tmp_path_obj.unlink()
        raise


def save_session_token(token: str, backend: StorageBackend) -> None:
    """Save token to specified storage backend.

    Args:
        token: The authentication token to store.
        backend: Where to store the token.

    Raises:
        KeyringUnavailableError: If keyring backend is requested but unavailable.
    """
    match backend:
        case StorageBackend.KEYRING:
            _save_to_keyring(token)
        case StorageBackend.FILE:
            _save_to_file(token)


def _get_from_env() -> str | None:
    """Get token from MONARCH_TOKEN environment variable."""
    return os.environ.get("MONARCH_TOKEN")


def _get_from_keyring() -> str | None:
    """Get token from OS keyring."""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        # Keyring may fail in headless environments
        return None


def _get_from_file() -> str | None:
    """Get token from JSON session file."""
    session_path = get_session_path()
    if not session_path.exists():
        return None
    try:
        with session_path.open() as f:
            data = json.load(f)
        # Handle corrupted/unexpected data types gracefully
        if not isinstance(data, dict):
            return None
        token = data.get("token")
        return token if isinstance(token, str) else None
    except (json.JSONDecodeError, OSError):
        return None


def legacy_artifact_exists() -> bool:
    """Report whether a legacy pickle session artifact exists.

    Uses filesystem metadata (``Path.exists()``) only. The file's contents are
    never read: pickle deserialization can execute arbitrary code, so legacy
    files are never treated as credentials and never deserialized.

    Returns:
        True if the legacy artifact file exists on disk.
    """
    try:
        return COMPAT_SESSION_PATH.is_file()
    except OSError:
        return False


def get_session_token() -> str | None:
    """Get token from the first available supported source.

    Checks in order:
    1. MONARCH_TOKEN environment variable
    2. OS keyring
    3. JSON session file

    Legacy pickle files are not consulted.

    Returns:
        The token if found, None otherwise.
    """
    # Check sources in precedence order
    token = _get_from_env()
    if token:
        return token

    token = _get_from_keyring()
    if token:
        return token

    token = _get_from_file()
    if token:
        return token

    return None


def _delete_from_keyring() -> None:
    """Delete token from OS keyring.

    Silently ignores errors if keyring is unavailable or token doesn't exist.
    """
    with contextlib.suppress(keyring.errors.KeyringError, Exception):
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)


def _delete_from_file() -> None:
    """Delete JSON session file."""
    session_path = get_session_path()
    if session_path.exists():
        session_path.unlink()


def delete_session_token(backend: StorageBackend | None = None) -> None:
    """Delete token from specified backend or all supported backends.

    Never touches the legacy pickle artifact (``~/.mm/mm_session.pickle``);
    cleanup of that file is always an explicit user action.

    Args:
        backend: Specific backend to clear, or None for all backends.
    """
    if backend is None:
        # Clear all supported backends
        _delete_from_keyring()
        _delete_from_file()
    else:
        match backend:
            case StorageBackend.KEYRING:
                _delete_from_keyring()
            case StorageBackend.FILE:
                _delete_from_file()


def has_valid_session() -> bool:
    """Check if a valid session token is available.

    Returns:
        True if a token is available from any source.
    """
    return get_session_token() is not None


def get_storage_info() -> dict[str, Any]:
    """Get detailed information about token storage status.

    Returns:
        Dict with:
        - has_env_token: bool
        - has_keyring_token: bool
        - has_file_token: bool
        - has_legacy_artifact: bool (filesystem presence only, never read)
        - active_backend: str | None (which source would be used)
    """
    has_env = _get_from_env() is not None
    has_keyring = _get_from_keyring() is not None
    has_file = _get_from_file() is not None
    has_legacy_artifact = legacy_artifact_exists()

    # Determine which backend would be active (first non-None in precedence).
    # Legacy pickle artifacts are never considered active credentials.
    active_backend: str | None = None
    if has_env:
        active_backend = "env"
    elif has_keyring:
        active_backend = StorageBackend.KEYRING.value
    elif has_file:
        active_backend = StorageBackend.FILE.value

    return {
        "has_env_token": has_env,
        "has_keyring_token": has_keyring,
        "has_file_token": has_file,
        "has_legacy_artifact": has_legacy_artifact,
        "active_backend": active_backend,
    }
