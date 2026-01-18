"""Session management with dual-backend token storage.

Supports keyring (secure, default), JSON file (portable), and legacy pickle (library compat).
"""

from __future__ import annotations

import contextlib
import json
import os
import pickle
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import keyring
import keyring.errors
import platformdirs

from .exceptions import ErrorCode, MonarchCLIError

if TYPE_CHECKING:
    from typing import Any

# Keyring constants
KEYRING_SERVICE = "com.monarch-cli"
KEYRING_USERNAME = "monarch-token"

# Legacy compat path (for monarchmoney library interop)
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


class StorageBackend(str, Enum):
    """Token storage backends in order of security preference."""

    KEYRING = "keyring"
    FILE = "file"
    FILE_COMPAT = "file-compat"


def get_config_dir() -> Path:
    """Get the config directory, respecting MONARCH_CONFIG_DIR env var.

    Returns:
        Path to config directory (created if needed).
    """
    env_dir = os.environ.get("MONARCH_CONFIG_DIR")
    config_dir = Path(env_dir) if env_dir else Path(platformdirs.user_config_dir("monarch-cli"))

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


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
    """Set secure file permissions (0600) if supported by the platform.

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


def _save_to_compat(token: str) -> None:
    """Save token to legacy pickle file for library interop."""
    COMPAT_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file for atomic write
    fd, tmp_path = tempfile.mkstemp(dir=COMPAT_SESSION_PATH.parent, suffix=".tmp")
    tmp_path_obj = Path(tmp_path)
    try:
        _set_file_permissions(fd)  # Set perms before writing (Unix only)
        with os.fdopen(fd, "wb") as f:
            # The library expects {"token": token} structure
            pickle.dump({"token": token}, f)
        os.replace(tmp_path, COMPAT_SESSION_PATH)
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
        case StorageBackend.FILE_COMPAT:
            _save_to_compat(token)


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


def _get_from_compat() -> str | None:
    """Get token from legacy pickle file."""
    if not COMPAT_SESSION_PATH.exists():
        return None
    try:
        with COMPAT_SESSION_PATH.open("rb") as f:
            data = pickle.load(f)  # noqa: S301 - Required for library compat
        # Handle corrupted/unexpected data types gracefully
        if not isinstance(data, dict):
            return None
        token = data.get("token")
        return token if isinstance(token, str) else None
    except (pickle.UnpicklingError, OSError, AttributeError, TypeError):
        return None


def get_session_token() -> str | None:
    """Get token from the first available source.

    Checks in order:
    1. MONARCH_TOKEN environment variable
    2. OS keyring
    3. JSON session file
    4. Legacy pickle file (library compat)

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

    token = _get_from_compat()
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


def _delete_from_compat() -> None:
    """Delete legacy pickle file."""
    if COMPAT_SESSION_PATH.exists():
        COMPAT_SESSION_PATH.unlink()


def delete_session_token(backend: StorageBackend | None = None) -> None:
    """Delete token from specified backend or all backends.

    Args:
        backend: Specific backend to clear, or None for all backends.
    """
    if backend is None:
        # Clear all backends
        _delete_from_keyring()
        _delete_from_file()
        _delete_from_compat()
    else:
        match backend:
            case StorageBackend.KEYRING:
                _delete_from_keyring()
            case StorageBackend.FILE:
                _delete_from_file()
            case StorageBackend.FILE_COMPAT:
                _delete_from_compat()


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
        - has_compat_token: bool
        - active_backend: str | None (which source would be used)
    """
    has_env = _get_from_env() is not None
    has_keyring = _get_from_keyring() is not None
    has_file = _get_from_file() is not None
    has_compat = _get_from_compat() is not None

    # Determine which backend would be active (first non-None in precedence)
    active_backend: str | None = None
    if has_env:
        active_backend = "env"
    elif has_keyring:
        active_backend = StorageBackend.KEYRING.value
    elif has_file:
        active_backend = StorageBackend.FILE.value
    elif has_compat:
        active_backend = StorageBackend.FILE_COMPAT.value

    return {
        "has_env_token": has_env,
        "has_keyring_token": has_keyring,
        "has_file_token": has_file,
        "has_compat_token": has_compat,
        "active_backend": active_backend,
    }
