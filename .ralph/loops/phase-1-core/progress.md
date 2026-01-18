# Phase 1 Core: Progress Log

This file tracks completed work and patterns learned during this loop.

---

## Codebase Patterns

### Exception Pattern
```python
# All exceptions follow this structure:
from monarch_cli.core.exceptions import AuthenticationError, ValidationError

# Raising with defaults:
raise AuthenticationError()  # Uses default message

# Raising with details:
raise NotFoundError(
    message="Account not found",
    resource_type="account",
    resource_id="abc123"
)

# Exit codes: 1 for auth/api/network errors, 2 for validation/usage errors
```

### Session Token Pattern
```python
from monarch_cli.core.session import (
    StorageBackend, get_session_token, save_session_token,
    delete_session_token, has_valid_session, get_storage_info
)

# Save token to keyring (default, secure)
save_session_token(token, StorageBackend.KEYRING)

# Save to file (for containers/portability)
save_session_token(token, StorageBackend.FILE)

# Get token (checks env -> keyring -> file -> compat in order)
token = get_session_token()

# Check if authenticated
if has_valid_session():
    # proceed

# Get detailed storage info (useful for auth status command)
info = get_storage_info()  # has_env_token, has_keyring_token, etc.

# Clear tokens (None = all backends)
delete_session_token()  # all
delete_session_token(StorageBackend.KEYRING)  # specific
```

---

## Completed Tasks

## [2026-01-18 09:09] - mc-a575 (Session Management Dual-Backend)
- Implemented StorageBackend enum: KEYRING, FILE, FILE_COMPAT
- Created get_config_dir() with MONARCH_CONFIG_DIR env override, uses platformdirs
- Created get_session_path() with MONARCH_SESSION_PATH env override
- Implemented save_session_token() with atomic writes (tempfile + rename) and 0600 perms
- Implemented get_session_token() with correct precedence: env -> keyring -> file -> compat
- Implemented delete_session_token() for specific or all backends
- Implemented has_valid_session() and get_storage_info() for status checking
- Keyring uses service='com.monarch-cli', username='monarch-token'
- Files changed: `src/monarch_cli/core/session.py`
- **Learnings:** When reading JSON/pickle into typed returns, use `isinstance()` check to satisfy mypy strict mode - `data.get("token")` returns Any, so need explicit validation
---

## [2026-01-18 09:07] - mc-7fb9 (Exception Hierarchy)
- Implemented ErrorCode enum with all 11 codes
- Created MonarchCLIError base class with message, code, details, exit_code attributes
- Implemented to_dict() for JSON-serializable structured output
- Created specific exceptions: AuthenticationError, AuthExpiredError, NotFoundError, ValidationError, APIError, RateLimitError, NetworkError
- Each exception has appropriate default message and error code
- ValidationError uses exit_code=2 (usage error), others use exit_code=1
- Files changed: `src/monarch_cli/core/exceptions.py`
- **Learnings:** Exception classes with typed optional parameters (resource_type, status_code, etc.) allow context-specific error messages while maintaining structured output for AI agents
---

## Patterns & Decisions

(recorded as tasks complete)

## Issues Encountered

(recorded as tasks complete)
