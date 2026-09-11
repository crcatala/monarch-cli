---
id: mc-sr92
status: open
deps: [mc-43s0]
links: [mc-2v9a]
created: 2026-09-11T12:39:30Z
type: task
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, safety, uploads, transport, credentials]
---
# Establish credential-safe third-party upload transport

Provide a reviewed adapter boundary for uploads to non-Monarch hosts that cannot forward Monarch authorization credentials, cookies, CSRF values, or session state.

The released `monarchmoneycommunity` 1.5.2 attachment path copies the authenticated client's headers into its Cloudinary request and removes cookie/CSRF headers but not token-mode `Authorization`. Because this CLI uses token authentication, transaction attachment upload must not ship until a safe transport path is available.

## Design

Prefer an upstream fix released in a compatible dependency version. If that is not available, implement a narrowly owned public adapter boundary that constructs third-party requests from an explicit destination-specific allowlist rather than copying authenticated Monarch request headers and removing known secrets. Command and service code must not call or depend directly on upstream private upload methods.

Keep this ticket limited to transport isolation and compatibility. File validation, attachment registration, staged mutation outcomes, retry policy, and transaction verification remain in `mc-2v9a` and the shared P0 mutation contracts.

## Key Decisions

- **Allowlist instead of denylist.** Third-party requests begin with only the headers and signed form fields required by that destination.
- **No credential-bearing redirect.** Redirect behavior must not carry sensitive headers to another origin.
- **A released upstream fix is preferred.** A local adapter implementation must document why it is necessary and which public compatibility boundary it owns.
- **Prepared requests are inspected in tests.** Credential isolation is verified at the transport boundary, not inferred from output redaction.

## Acceptance Criteria

- [ ] The transaction-attachment upload path uses a public adapter interface that does not expose upstream private methods to commands or services.
- [ ] Requests to third-party hosts contain no Monarch `Authorization`, cookie, CSRF, session, or other credential-bearing headers.
- [ ] Third-party request headers and signed fields are constructed from an explicit destination-specific allowlist rather than copied from the authenticated Monarch client.
- [ ] Redirect handling cannot forward sensitive headers across origins and is covered by a regression test.
- [ ] Tests inspect prepared or captured outbound requests for token-authenticated and cookie-authenticated client states and fail if credential material is present.
- [ ] Logs, structured errors, debug output, and test failures redact signed upload parameters and credentials.
- [ ] The implementation uses a compatible released upstream fix when available; otherwise the local adapter boundary and its maintenance/version assumptions are documented.
- [ ] Dependency metadata and clean-install compatibility require the safe upstream release when that path is selected.
- [ ] No file-validation policy, attachment registration workflow, mutation outcome, retry behavior, or transaction command is implemented in this ticket.
- [ ] Security documentation and repository verification are complete.
