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

Support users whose Monarch sessions cannot be established or used reliably with token-only authentication. Browser-derived cookies are needed for some CAPTCHA-constrained or otherwise incompatible login paths, so the CLI needs a deliberate cookie mode that works for humans and automation without exposing secrets in shell history, process arguments, logs, or output.

Cookie authentication is a credential-model change, not merely another login flag. It must preserve deterministic credential precedence, secure storage, diagnostics, logout behavior, and non-interactive guarantees.

## Design

Introduce a versioned typed session record with mutually exclusive `token` and `cookie` modes. Cookie records retain only the two fields required by the verified upstream 1.5.2 client: `session_id` and `csrftoken`; unrelated browser cookies are discarded. The adapter constructs the upstream client and applies the selected mode, keeping upstream details out of command handlers.

Credential precedence remains source-based: `MONARCH_TOKEN`, then keyring, then atomic JSON session file. Each keyring/file source contains at most one explicit session mode; mode does not create a second precedence axis. Existing raw-token keyring and `{\"token\": ...}` JSON records remain readable and are rewritten as versioned records on the next successful save. Legacy pickle is never read, written, migrated, or deleted.

Provide one initial secret-safe input surface: `auth login --cookie-file PATH`, where `-` reads a browser Cookie-header value from stdin. Do not accept cookie values directly in argv. A named file must be a readable regular file; on POSIX, reject group/world-readable cookie input files. Do not print the path or cookie material. The non-interactive policy guards stdin before any read.

Use upstream cookie login/verification only with persistence disabled (`save_session=False`), then persist through the CLI's keyring or JSON backend. POSIX JSON writes are atomic and mode `0600`; Windows behavior follows the accurate platform limitations established by `mc-2nj4`.

Verification can reliably distinguish malformed/missing fields, unsupported session data, network failure, and invalid-or-expired credentials. It must not claim to distinguish expiration from invalidity when the upstream service does not. Cookie rotation/refresh is not supported by the verified client and is out of scope; users re-import cookies when authentication fails.

## Key Decisions

- **Typed versioned sessions.** Token and cookie credentials can never be mistaken for one another.
- **Source precedence is unchanged.** Environment token > keyring session > JSON session file.
- **Minimum cookie storage.** Persist only `session_id` and `csrftoken`.
- **One initial input contract.** `--cookie-file PATH|-`; no cookie argv value.
- **CLI-owned persistence only.** Upstream pickle persistence is always disabled.
- **Honest expiry semantics.** Report invalid-or-expired unless the server provides a reliable distinction.
- **Conservative compatibility floor.** Require `monarchmoneycommunity>=1.5.2`, the verified cookie-capable release.

## Acceptance Criteria

- [ ] A versioned session type represents exactly one of token or cookie mode and validates malformed, mixed, or unsupported records before client creation.
- [ ] `auth login --cookie-file PATH|-` establishes a cookie session from a protected regular file or stdin without accepting cookie material directly in argv.
- [ ] Cookie input requires `session_id` and `csrftoken`, discards unrelated cookies, and rejects duplicates/malformed input deterministically.
- [ ] On POSIX, named cookie input files with group/world permissions are rejected; platform-specific limitations are documented accurately.
- [ ] Cookie values and unintended input paths never appear in help, process arguments, logs, errors, diagnostics, human output, or structured output, including sanitized upstream failures.
- [ ] Credential precedence is exactly `MONARCH_TOKEN` > keyring session > JSON session file and is documented/tested across token and cookie modes.
- [ ] Existing raw-token keyring values and legacy `{\"token\": ...}` JSON files remain readable and migrate only when a successful save occurs.
- [ ] Cookie verification invokes the upstream client with `save_session=False`; tests prove no `~/.mm` pickle file is created, read, overwritten, or deleted.
- [ ] Keyring and JSON storage, status, doctor/ping, logout, adapter reset, and backend-specific deletion handle both explicit modes consistently.
- [ ] JSON persistence is atomic and mode `0600` on POSIX; Windows guarantees are documented without claiming POSIX owner-only semantics.
- [ ] Authentication failures distinguish missing/malformed fields, unsupported session data, network failure, and invalid-or-expired cookies with stable sanitized errors and actionable re-import guidance.
- [ ] Cookie refresh/rotation is not claimed; failed validity requires explicit user re-import.
- [ ] Interactive and non-interactive flows never hang and preserve documented stdout/stderr and exit-code contracts.
- [ ] `auth status --json` exposes a documented stable `auth_mode` and storage-source contract without exposing credential values.
- [ ] Tests cover success, stdin/file input, malformed/missing/extra fields, insecure files, storage failures, legacy token compatibility, precedence, redaction of adversarial upstream text, verification failure, logout, and human/machine output.
- [ ] Project metadata requires `monarchmoneycommunity>=1.5.2`; the clean-install harness established by `mc-43s0` verifies the cookie methods without using upstream session persistence.
- [ ] User-facing security/authentication and migration documentation is complete and repository verification passes.
