---
id: mc-2nj4
status: open
deps: []
links: []
created: 2026-09-11T01:15:13Z
type: bug
priority: 0
assignee: cc-vps
parent: mc-cr09
tags: [p0, security, authentication, session, migration]
---
# Remove implicit legacy pickle session loading and provide safe migration

Eliminate automatic deserialization of legacy pickle session files. Pickle can execute code while loading, so implicitly reading a file from a compatibility path creates an avoidable local code-execution boundary. Legacy session compatibility should not silently override the safety properties of the primary keyring and atomic JSON storage paths.

Users who still have a legacy session need a deliberate, understandable migration path that preserves access without keeping unsafe automatic loading enabled.

## Design

Inventory all compatibility-session read and write paths and their precedence. Default authentication lookup should never deserialize pickle. If migration support is retained, make it an explicit one-time action with clear consent, restrictive permission checks, validation of the minimal expected data shape, secure storage into the supported backend, and cleanup or quarantine of the legacy file.

Because unpickling is inherently unsafe, an agent should evaluate whether an in-process pickle migration can be made acceptable at all. A forced re-login may be the safer supported path. Do not imply that file ownership or mode checks make hostile pickle deserialization safe.

## Acceptance Criteria

- [ ] Normal CLI startup and authentication lookup never call `pickle.load` or otherwise deserialize a legacy pickle.
- [ ] Legacy compatibility files are excluded from default credential precedence.
- [ ] Users with a legacy file receive actionable guidance to re-authenticate or perform an explicit supported migration.
- [ ] Any retained migration path requires explicit user action and documents the residual risk before deserialization.
- [ ] Supported session storage uses keyring or atomic JSON with owner-only permissions on supported platforms.
- [ ] Existing supported sessions continue to work without migration.
- [ ] Logout and diagnostics correctly identify and handle legacy artifacts without loading them.
- [ ] Tests use a payload that would fail if unpickling is attempted and prove default commands never execute it.
- [ ] Security and migration behavior is documented, including removal/deprecation timing for legacy compatibility.

