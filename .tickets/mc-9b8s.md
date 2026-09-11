---
id: mc-9b8s
status: open
deps: [mc-43s0, mc-2nj4, mc-2btg]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, authentication, cookies, security, automation]
---
# Add secure cookie-based authentication

Support users whose Monarch sessions cannot be established or used reliably with token-only authentication. Some authentication paths require browser-derived session cookies, so the CLI needs a deliberate cookie-based mode that works for humans and automation without exposing sensitive cookie material in shell history, process arguments, logs, or command output.

This expands authentication compatibility while preserving the CLI's existing credential precedence, secure storage expectations, diagnostics, logout behavior, and non-interactive guarantees. Cookie authentication is a credential-handling feature, not merely another login flag, and should be designed around an explicit session model.

## Design

Design the supported session representation and adapter boundary before adding CLI options. Prefer secret input through stdin or a protected file/interactive prompt rather than command-line values. Store only the minimum required cookie fields using the established secure session backend, with atomic owner-only file writes where file storage is supported; do not introduce pickle persistence.

Token and cookie sessions should have explicit types and deterministic precedence. Authentication diagnostics should identify the active mode without printing secrets. Verification, expiration/failure behavior, migration, keyring representation, and cookie rotation should be considered. Keep upstream-client details out of command handlers.

## Acceptance Criteria

- [ ] Users can establish an authenticated session using the minimum required cookie material through at least one secret-safe input path.
- [ ] Cookie values are never accepted in a way that exposes them in normal process arguments by default, and are never printed in help, logs, errors, diagnostics, or structured output.
- [ ] Cookie sessions are represented explicitly and do not get mistaken for token sessions.
- [ ] Credential precedence between environment, keyring, supported session files, token sessions, and cookie sessions is deterministic and documented.
- [ ] Supported file persistence is atomic and owner-only on applicable platforms; no pickle serialization or implicit legacy-session loading is introduced.
- [ ] Keyring storage, file storage, status, doctor/ping, logout, and client reset behavior handle cookie sessions consistently.
- [ ] Authentication verification distinguishes invalid/expired cookies, missing required fields, network failure, and unsupported session data with actionable errors.
- [ ] Interactive and non-interactive flows never hang and preserve documented stdout/stderr and exit-code contracts.
- [ ] Tests prove secrets are redacted and cover successful setup, malformed input, missing fields, storage failures, precedence, verification failure, logout, and both output modes.
- [ ] The required upstream-client compatibility floor is declared in project metadata and verified by a clean-install test.
- [ ] User-facing security and authentication documentation is complete and repository verification passes.
