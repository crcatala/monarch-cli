---
id: mc-frmf
status: open
deps: [mc-2v9a]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, receipts, uploads, automation, mutations, safety]
---
# Add secure receipt-inbox upload

Allow a receipt to be submitted to the household receipt inbox for automated processing and matching when the target transaction is not yet known. This supports capture-first workflows that differ from attaching a document to an existing transaction and can reduce manual receipt categorization.

Receipt contents are sensitive financial documents, and upload processing may continue asynchronously after the initial request. The command therefore needs clear file policy, mutation authorization, retry behavior, and honest processing-status semantics.

## Design

Model inbox upload as its own receipt workflow rather than an attachment mode requiring a transaction ID. Reuse shared file-validation and upload primitives where appropriate, but keep result semantics distinct: acceptance for processing is not the same as successful categorization or transaction matching.

Validate metadata before reading or transmitting content. Avoid exposing local paths or contents in output. Disable unsafe automatic retries, and return any remote receipt/sync identifier and observed processing state needed for later inspection. A dry-run, if supported, must not read or upload file bytes unnecessarily.

## Acceptance Criteria

- [ ] A user can submit a supported readable receipt file without specifying a transaction ID.
- [ ] The workflow is clearly distinct from attaching a file to an existing transaction.
- [ ] Upload is blocked by default and requires shared mutation authorization.
- [ ] Nonexistent, unreadable, directory, empty, unsupported, and policy-exceeding files fail before any remote mutation.
- [ ] Validation defines supported file types, size policy, filename handling, and the limits of content validation.
- [ ] Output never includes receipt contents, credentials, or unintended local path information.
- [ ] The command distinguishes upload acceptance, processing in progress, completed/matched states when observable, rejection, ambiguous transport failure, and unknown status.
- [ ] A potentially successful upload is not automatically repeated after timeout or disconnect.
- [ ] Stable output includes available remote receipt/sync identity, safe filename metadata, size, and processing status without claiming categorization or matching prematurely.
- [ ] A dry-run, if implemented, performs no remote call and does not unnecessarily read file contents.
- [ ] Tests cover authorization, validation, success, asynchronous status, rejection, ambiguity, redaction, dry-run, and output modes without live financial API access.
- [ ] The required upstream-client compatibility floor is declared and covered by clean-install verification.
- [ ] Privacy/safety documentation and repository verification are complete.
