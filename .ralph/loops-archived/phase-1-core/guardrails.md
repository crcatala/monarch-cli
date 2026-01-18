# Phase 1 Core Guardrails

## Security Requirements

1. **Never log or print tokens**. Not in debug output, not in error messages, nowhere.

2. **Session file permissions**: Always 0600 (owner read/write only)

3. **Atomic writes**: Use tempfile + rename pattern for session files to prevent corruption

4. **No secrets in CLI flags**: The adapter should ONLY get tokens from session storage or env vars

## Code Patterns

### Error Handling
```python
# All custom exceptions inherit from MonarchCLIError
from .exceptions import MonarchCLIError, AuthenticationError

# Exceptions have structured output for AI agents
raise AuthenticationError()  # Has default message, code, exit_code
```

### Async Bridge
```python
# Always use run_async() for monarchmoney calls
from .async_utils import run_async
result = run_async(client.get_accounts())
```

### Token Access
```python
# Only adapter.py imports from monarchmoney
from monarchmoney import MonarchMoney

# Use constructor parameter, not private attributes
client = MonarchMoney(token=token)  # ✅
client._headers["Authorization"] = ...  # ❌ Never do this
```

## Testing

- Write unit tests for date utilities (pure functions, easy to test)
- Session management can be tested with temp directories
- Adapter can be tested with mocked MonarchMoney class

## Reference

- Implementation details: `plans/monarch-cli-implementation-plan.md` (Phase 1 section)
- Tickets: `.tickets/mc-7fb9.md`, `.tickets/mc-a575.md`, `.tickets/mc-dcbf.md`, `.tickets/mc-79ca.md`, `.tickets/mc-c0c3.md`, `.tickets/mc-7bd9.md`
