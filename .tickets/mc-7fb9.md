---
id: mc-7fb9
status: open
deps: [mc-9441]
links: []
created: 2026-01-18T16:00:42Z
type: task
priority: 0
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, core, errors]
---
# Exception Hierarchy

Create centralized exception hierarchy for consistent error handling across the CLI.

## Location
`src/monarch_cli/core/exceptions.py`

## Error Codes (ErrorCode enum)
These codes are designed for AI agent consumption:
| Code | Meaning |
|------|---------|
| AUTH_REQUIRED | Not authenticated |
| AUTH_EXPIRED | Session token expired |
| AUTH_FAILED | Bad credentials |
| NOT_FOUND | Resource not found |
| INVALID_INPUT | Input validation error |
| API_ERROR | Monarch Money API error |
| RATE_LIMITED | Rate limit exceeded |
| NETWORK_ERROR | Connection/network issues |
| TIMEOUT | Request timeout |
| UPSTREAM_UNAVAILABLE | Monarch Money service down |
| UNKNOWN | Catch-all for unexpected errors |

## Exception Classes
```python
class MonarchCLIError(Exception):
    """Base exception with code, message, details, exit_code."""
    def to_dict(self) -> dict:  # For JSON error output

class AuthenticationError(MonarchCLIError):
    """Not authenticated. Run 'monarch auth login' first."""

class AuthExpiredError(MonarchCLIError):
    """Session expired. Re-authenticate."""

class NotFoundError(MonarchCLIError):
    """Resource not found (includes resource_type and resource_id)."""

class ValidationError(MonarchCLIError):
    """Input validation error (exit_code=2 for usage errors)."""

class APIError(MonarchCLIError):
    """Monarch Money API error (includes status_code)."""

class RateLimitError(MonarchCLIError):
    """Rate limit exceeded (includes retry_after_seconds)."""

class NetworkError(MonarchCLIError):
    """Network connectivity error."""
```

## Mapping from Upstream Exceptions
| Upstream Exception | Our Exception |
|-------------------|---------------|
| RequireMFAException | (handled in login flow) |
| LoginFailedException | AuthenticationError |
| RequestFailedException | APIError |
| aiohttp.ClientError | NetworkError |
| asyncio.TimeoutError | NetworkError |

## Exit Codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (auth, API, network) |
| 2 | Usage error (bad arguments) |
| 130 | Interrupted (Ctrl-C) |

## Acceptance Criteria

- [ ] ErrorCode enum with all codes
- [ ] MonarchCLIError base class with to_dict() method
- [ ] All specific exception classes implemented
- [ ] Proper exit codes assigned (1 for most, 2 for ValidationError)
- [ ] Exceptions include relevant details (resource_id, status_code, etc.)
- [ ] Unit tests for exception serialization

