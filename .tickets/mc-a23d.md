---
id: mc-a23d
status: closed
deps: [mc-96b1]
links: []
created: 2026-01-18T16:00:10Z
type: epic
priority: 0
assignee: cc-vps
tags: [phase-1, auth, core]
---
# Epic 1: Authentication Foundation

Implement the authentication foundation including core utilities, session management, and auth commands.

## Background
Authentication is implemented first so that all subsequent features can be live-tested against the real Monarch Money API. The `monarchmoneycommunity` library provides async methods and uses 'Token' prefix authentication (not Bearer).

## Why Auth First?
By implementing authentication early, developers can:
1. Authenticate once with `monarch auth login`
2. Live-test every subsequent feature as it's built
3. Write integration tests alongside implementation
4. Validate output formats against actual data

## Scope
This epic covers the entire core infrastructure layer:
- Async utilities for running async code from sync Typer commands
- Exception hierarchy for consistent error handling
- Error handler decorator
- Dual-backend session management (keyring + file)
- Adapter pattern to isolate upstream library details
- Retry logic with exponential backoff
- Date utilities and presets
- Minimal output helpers (bootstrap version)
- Main entry point
- Auth commands (login, status, logout, doctor, ping, setup)

## Key Technical Decisions
1. **Token handling**: Use library's constructor `token=` parameter, not private attributes
2. **Storage backends**: Keyring (secure, default) or JSON session file (portable, 0600 perms)
3. **Adapter pattern**: All access to monarchmoneycommunity private attributes isolated in adapter.py
4. **Error codes**: Structured error codes (AUTH_REQUIRED, API_ERROR, etc.) for AI agent consumption

## Auth Commands Overview
| Command | Purpose |
|---------|---------|
| `monarch auth login` | Interactive login with MFA support |
| `monarch auth status` | Check authentication state |
| `monarch auth logout` | Remove stored tokens |
| `monarch auth doctor` | Diagnose environment and storage |
| `monarch auth ping` | Test API connectivity |
| `monarch auth setup` | Show setup instructions |

## Acceptance Criteria

- [ ] `monarch auth login` works with email/password and MFA
- [ ] `monarch auth status` shows authentication state and storage backend
- [ ] `monarch auth logout` clears tokens from all backends
- [ ] `monarch auth doctor` diagnoses keyring, files, and API connectivity
- [ ] `monarch auth ping` returns ok/error status
- [ ] Session persists across CLI invocations
- [ ] Keyring storage works when available
- [ ] File storage works as fallback with 0600 permissions
- [ ] MONARCH_TOKEN env var works for CI/automation
- [ ] All auth errors have proper error codes


## Notes

**2026-01-18T16:17:30Z**

## 🔴 HUMAN CHECKPOINT AT END OF EPIC

After Epic 1 is complete, human intervention required:

1. **Run auth login** - provide credentials interactively
2. **Verify token works** - check `monarch auth ping`
3. **Sanity check data** - verify `monarch accounts list` shows real accounts

This is the ONLY blocking human checkpoint until PyPI publishing.

After authentication, agents can:
- Live-test all subsequent features
- Verify transforms against real API responses
- Run integration tests

**Recommendation**: Complete this checkpoint immediately after Phase 1 to unblock all subsequent work.
