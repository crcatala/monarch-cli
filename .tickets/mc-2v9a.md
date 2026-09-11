---
id: mc-2v9a
status: open
deps: [mc-k48z, mc-t9o7, mc-hszv]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, transactions, attachments, uploads, mutations, safety]
---
# Add safe transaction attachment upload

Allow receipts and supporting documents to be attached to a known transaction from the CLI. This removes a manual UI step and enables receipt-management workflows, while introducing file handling, potentially sensitive uploads, and ambiguous network-failure risks that require careful safeguards.

## Design

Implement attachment upload as a focused transaction workflow behind the shared mutation authorization and retry-safe execution layers. Validate the local path and file metadata before authentication or upload, preserve the chosen filename explicitly, and define practical file-size/type behavior without claiming stronger validation than is available. A dry-run may report intended metadata but must never read or transmit file contents unnecessarily. Keep optional follow-up transaction edits out of the first implementation unless partial-success semantics are fully supported.

## Acceptance Criteria

- [ ] A user can attach a readable local file to an explicitly identified transaction.
- [ ] Upload is blocked by default and requires the shared mutation authorization mechanism.
- [ ] Nonexistent, unreadable, directory, empty, and policy-exceeding files fail before any remote mutation.
- [ ] The local path is never exposed as the remote filename unless explicitly intended, and output does not include file contents or credentials.
- [ ] A dry-run, if provided, performs no upload and reports only safe metadata needed to review the action.
- [ ] Ambiguous timeout/disconnect behavior does not automatically repeat a potentially successful upload.
- [ ] The stable mutation result reports transaction ID, remote attachment identity when available, filename, size, status, and any ambiguous/partial outcome.
- [ ] Tests use mocked file and API boundaries and cover authorization, validation, dry-run, success, server rejection, timeout, and output modes.
- [ ] No live financial API call is required by the default test suite.
- [ ] User-facing safety documentation and repository verification are complete.

