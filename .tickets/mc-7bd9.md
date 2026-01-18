---
id: mc-7bd9
status: closed
deps: [mc-a575, mc-7fb9]
links: []
created: 2026-01-18T16:01:36Z
type: task
priority: 0
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, core, adapter]
---
# Adapter Module (Isolates Upstream Library)

Create adapter layer to isolate monarchmoneycommunity library details and protect against upstream changes.

## Location
`src/monarch_cli/core/adapter.py`

## Purpose
The adapter pattern creates a boundary between our CLI code and the upstream library. All access to library internals (private attributes, undocumented behavior) is isolated here. If the upstream library changes, we only need to update this file.

## Key Functions
```python
_client: MonarchMoney | None = None

def get_authenticated_client() -> MonarchMoney:
    """Get authenticated MonarchMoney client.
    
    Uses the library's constructor token= parameter for clean initialization.
    The library handles setting _headers["Authorization"] = "Token {token}".
    """
    global _client
    if _client is not None:
        return _client

    token = get_session_token()
    if not token:
        raise AuthenticationError()

    # Pass token via constructor - cleanest approach
    _client = MonarchMoney(token=token)
    return _client

def extract_token_from_client(client: MonarchMoney) -> str | None:
    """Extract token from client after login.
    
    The library exposes a `token` property, so we use that instead of _token.
    """
    return client.token

def reset_client() -> None:
    """Reset cached client (for logout)."""
    global _client
    _client = None
```

## Token Handling Details
The monarchmoneycommunity library:
- Uses 'Token' prefix (not 'Bearer')
- Exposes `client.token` property for reading
- Handles header setup internally when `token=` passed to constructor

## Why Cache the Client?
- Avoids recreating client for each command
- Token validation happens once per session
- Reset on logout to ensure fresh client on next login

## Future Considerations
If retry logic is needed at the client level, it can be added here:
```python
def get_authenticated_client() -> MonarchMoney:
    # Could add retry wrapper around client methods
    # Could add timeout configuration
    ...
```

## Acceptance Criteria

- [ ] get_authenticated_client() returns configured client
- [ ] Raises AuthenticationError when no token available
- [ ] extract_token_from_client() works after login
- [ ] reset_client() clears cached client
- [ ] Uses constructor token= parameter (not private attributes)
- [ ] Client is cached for reuse
- [ ] Unit tests with mocked MonarchMoney

