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

### Async Bridge Pattern
```python
from monarch_cli.core.async_utils import run_async

# Execute any async coroutine synchronously
accounts = run_async(client.get_accounts())

# Handles KeyboardInterrupt and CancelledError appropriately
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

### Retry Pattern
```python
from monarch_cli.core.retry import with_retry
from monarch_cli.core.async_utils import run_async

# Basic retry (uses defaults: 3 retries, exponential backoff with jitter)
result = run_async(with_retry(lambda: client.get_accounts()))

# Custom retry settings
result = run_async(with_retry(
    lambda: client.get_accounts(),
    max_retries=5,
    base_delay=0.5,
    max_delay=60.0,
    jitter=True,
))

# Note: coro_factory is a lambda/callable that RETURNS a coroutine
# This allows fresh coroutine creation for each retry attempt
```

### Date Utilities Pattern
```python
from datetime import date
from monarch_cli.core.dates import DatePreset, resolve_preset, parse_date_range

# Resolve a preset to concrete dates
start, end = resolve_preset(DatePreset.THIS_MONTH)
# Returns (date(2026, 1, 1), date(2026, 1, 18))

# Parse to ISO format strings (for API calls)
start_str, end_str = parse_date_range(DatePreset.LAST_30_DAYS)
# Returns ('2025-12-19', '2026-01-18')

# Explicit dates take precedence over preset
start_str, end_str = parse_date_range(
    preset=DatePreset.THIS_MONTH,
    start=date(2026, 1, 10),  # Overrides preset start
)
# Returns ('2026-01-10', '2026-01-18')

# ALL preset returns no filter
start_str, end_str = parse_date_range(DatePreset.ALL)
# Returns (None, None)
```

---

## Completed Tasks

## [2026-01-18 09:13] - mc-c0c3 (Date Utilities and Presets)
- Created DatePreset StrEnum with all 12 presets: TODAY, YESTERDAY, THIS_WEEK, LAST_WEEK, THIS_MONTH, LAST_MONTH, LAST_30_DAYS, LAST_90_DAYS, THIS_YEAR, LAST_YEAR, YTD, ALL
- Implemented resolve_preset() with Python match statement for clean handling
- THIS_WEEK starts on Monday (weekday() == 0)
- YTD is alias for THIS_YEAR (handled via `case DatePreset.THIS_YEAR | DatePreset.YTD`)
- ALL returns (None, None) for no date filtering
- Implemented parse_date_range() returning ISO format strings
- Explicit start/end dates take precedence over preset
- Files changed: `src/monarch_cli/core/dates.py`
- **Learnings:** StrEnum provides nice string values for CLI args. Python match with `|` pattern works well for aliases.
---

## [2026-01-18 09:12] - mc-79ca (Retry Logic with Exponential Backoff)
- Created with_retry[T]() async function using PEP 695 type parameters
- RETRYABLE_EXCEPTIONS tuple: ConnectionError, TimeoutError, OSError
- Exponential backoff: delay = min(base_delay * 2^attempt, max_delay)
- Jitter adds randomness (0.75 to 1.25 multiplier) to prevent thundering herd
- Raises NetworkError with details after max_retries exceeded
- Uses coro_factory pattern (callable returning coroutine) for retryability
- Files changed: `src/monarch_cli/core/retry.py`
- **Learnings:** Use keyword-only args (after `*`) for optional parameters with defaults to improve API clarity and prevent positional arg mistakes
---

## [2026-01-18 09:11] - mc-dcbf (Async Utilities Module)
- Created run_async[T]() generic function using PEP 695 type parameters
- Uses asyncio.run() to execute coroutines
- Properly propagates KeyboardInterrupt without wrapping
- Converts asyncio.CancelledError to RuntimeError with clear message
- Files changed: `src/monarch_cli/core/async_utils.py`
- **Learnings:** Use PEP 695 `def func[T]()` syntax for generic type parameters (ruff UP047). Import Coroutine from collections.abc, not typing (ruff UP035).
---

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
