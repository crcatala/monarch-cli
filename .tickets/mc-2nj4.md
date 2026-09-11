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
# Remove legacy pickle session support and require safe re-authentication

Eliminate all serialization and deserialization of legacy pickle session files. Pickle can execute code while loading, so reading a compatibility file creates an avoidable local code-execution boundary. Legacy session compatibility must not weaken the safety properties of the supported environment, keyring, and atomic JSON credential paths.

Users who only have a legacy session will need to authenticate again. Backward compatibility with the pickle format is intentionally not required for the next major release.

## Design

Remove pickle from credential lookup, storage, and the `StorageBackend` model. Do not provide an in-process migration command, restricted unpickler, or other mechanism that deserializes the old file: validation occurs after deserialization and cannot make hostile pickle data safe.

The legacy path may be inspected only as a filesystem artifact. `auth status`, `auth doctor`, and authentication failures should report that the artifact exists without reading its contents, explain that it is not an active credential, and direct the user to `monarch auth login`. After re-authentication, users may delete the file themselves using documented instructions; the CLI must not implicitly delete or quarantine it. No `file-compat` login, logout, or storage option is retained.

Supported credential precedence after this change is:
1. `MONARCH_TOKEN`
2. System keyring
3. Atomic JSON session file

File-backed session writes remain atomic. On POSIX, the resulting credential file must have mode `0600`; Windows behavior and platform limitations must be documented accurately rather than described as POSIX owner-only permissions.

## Key Decisions

- **Forced re-authentication, not pickle migration.** No ownership, mode, or post-load shape check can make arbitrary pickle deserialization safe.
- **Remove compatibility rather than deprecate it in place.** The change is intended for a major release, so the enum member, read/write helpers, and CLI options can be removed together.
- **Detect presence only.** Diagnostics may use filesystem metadata such as `exists()` but must never inspect pickle contents.
- **No implicit cleanup.** Re-authentication must not destroy the legacy artifact; cleanup remains an explicit user action.

## Acceptance Criteria

- [ ] Production code contains no pickle serialization or deserialization for session handling, including `pickle.load`, `pickle.loads`, `pickle.dump`, and `pickle.dumps`.
- [ ] `StorageBackend.FILE_COMPAT`, `_get_from_compat`, `_save_to_compat`, and the `file-compat` CLI surface are removed.
- [ ] Normal startup, credential lookup, authenticated commands, `auth status`, and `auth doctor` never read the contents of a legacy pickle file.
- [ ] Legacy compatibility files are never considered active credentials and are absent from credential precedence.
- [ ] When a legacy artifact exists without a supported credential, status, diagnostics, and representative authentication failures identify it as unsupported and direct the user to `monarch auth login`.
- [ ] Diagnostics report legacy artifact presence using filesystem metadata only and do not call code capable of deserializing it.
- [ ] Re-authentication stores the new session only in keyring or atomic JSON storage and does not implicitly delete or quarantine the legacy artifact.
- [ ] Atomic JSON writes produce mode `0600` on POSIX; supported Windows behavior and limitations are tested or documented without making an inaccurate owner-only claim.
- [ ] Existing environment, keyring, and JSON sessions continue to work with the documented precedence.
- [ ] Regression tests place a hostile sentinel pickle at the legacy path and prove `get_session_token`, `auth status`, `auth doctor`, and a representative authenticated command do not execute or deserialize it.
- [ ] Logout and diagnostics can operate safely when a malformed or hostile legacy artifact exists.
- [ ] Security, re-authentication, manual cleanup, and major-release removal behavior are documented.
- [ ] Repository verification passes.
