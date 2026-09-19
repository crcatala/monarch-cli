---
id: mc-sr92
status: closed
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

Prefer an upstream fix released in a compatible dependency version. If that is not available, implement a narrowly owned public adapter boundary that constructs third-party requests from an explicit destination-specific allowlist rather than copying authenticated Monarch request headers and removing known secrets. Command and service code must not call or depend directly on upstream private upload methods, and must not call the existing public `MonarchMoney.upload_attachment()` method directly because it hides the unsafe third-party transport and does not expose stage-level outcomes.

The public boundary consumed by `mc-2v9a` must make the third-party media-upload stage explicit and keep it separate from the authenticated Monarch operations that obtain signed parameters and register the attachment. A merely fixed monolithic upload method is sufficient only if it also provides the stage-level observability required for `mutation-outcome.v1`; otherwise the adapter layer must own the compatibility decomposition behind this boundary. Commands and services never call upstream private methods directly. This ticket owns only the safe third-party transport and its compatibility boundary; `mc-2v9a` owns authenticated workflow orchestration and file policy.

Keep this ticket limited to transport isolation and compatibility. File validation, attachment registration, staged mutation outcomes, retry policy, and transaction verification remain in `mc-2v9a` and the shared P0 mutation contracts.

## Key Decisions

- **Allowlist instead of denylist.** Third-party requests begin with only the headers and signed form fields required by that destination.
- **No credential-bearing redirect.** Redirect behavior must not carry sensitive headers to another origin.
- **A released upstream fix is preferred.** A local adapter implementation must document why it is necessary and which public compatibility boundary it owns.
- **Prepared requests are inspected in tests.** Credential isolation is verified at the transport boundary, not inferred from output redaction.
- **The media transport is a narrow public boundary.** Its conceptual input is a validated file plus signed destination parameters; its result contains only the media-host identity/metadata needed by the attachment workflow. It does not expose the upstream client's private methods or a generic arbitrary-URL request primitive.
- **Signed material is sensitive.** Signed form fields, upload responses, and destination details are treated as sensitive transport data and are never logged, emitted in structured errors, or copied into diagnostics.

## Acceptance Criteria

- [ ] The transaction-attachment upload path uses a public adapter interface that does not expose upstream private methods to commands or services.
- [ ] No command or service calls `MonarchMoney.upload_attachment()` directly; the consumed boundary makes the third-party media-upload stage explicit and preserves enough stage identity/result information for `mc-2v9a` to classify success, definitive failure, ambiguity, and partial completion.
- [ ] Requests to third-party hosts contain no Monarch `Authorization`, cookie, CSRF, session, or other credential-bearing headers, regardless of whether the authenticated client uses token or cookie mode.
- [ ] Third-party request headers and signed fields are constructed from an explicit destination-specific allowlist rather than copied from the authenticated Monarch client.
- [ ] The destination host is constrained to the verified upload endpoint, and redirect handling cannot forward sensitive headers across origins; both policies are covered by regression tests.
- [ ] The public transport boundary does not become a generic arbitrary-URL HTTP client or expose signed parameters to callers that do not need them.
- [ ] Tests inspect prepared or captured outbound requests for token-authenticated and cookie-authenticated client states and fail if credential material is present.
- [ ] Logs, structured errors, debug output, and test failures redact signed upload parameters and credentials.
- [ ] The implementation uses a compatible released upstream fix when available; otherwise the local adapter boundary and its maintenance/version assumptions are documented.
- [ ] A dependency version bump alone is not accepted as evidence of safety: prepared-request tests prove the selected upstream release or local adapter omits credential-bearing headers and preserves the required stage boundary.
- [ ] Dependency metadata and clean-install compatibility require the safe upstream release when that path is selected.
- [ ] No file-validation policy, attachment registration workflow, mutation outcome, retry behavior, or transaction command is implemented in this ticket.
- [ ] Security documentation and repository verification are complete.

## Notes

**2026-09-19T17:51:52Z**

Live credential-safety verification — 2026-09-19, disposable test account.

Performed a real `transactions attachments add` upload with outbound HTTP instrumented in-process (request header NAMES only, no values, no repo changes).

Result:
- Third-party media request: `POST api.cloudinary.com/v1_1/monarch-money/image/upload/` with header names `['User-Agent']`, 0 session cookies, 0 sensitive headers.
- Control (read-only Monarch call under the same instrumentation): Monarch session default header names `['Accept','Authorization','Client-Platform','Content-Type','User-Agent']` — i.e. the instrumentation detects `Authorization` and it was absent from the media request.

This is a live end-to-end proof of the ticket's primary acceptance criterion (no Monarch credential header reaches the media host), stronger than the request-level unit test.
