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

---

## Completed Tasks

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
