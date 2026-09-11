---
id: mc-2v9a
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv]
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

Add `transactions attachments add TRANSACTION_ID PATH` as a three-stage remote workflow: obtain transaction-specific signed upload parameters, upload the asset to the third-party media host, then register that asset on the transaction. Each stage has distinct definitive, ambiguous, and partial outcomes; successful media upload followed by failed registration may leave an orphaned asset, while a lost registration response may leave an attachment that exists remotely but is not yet known locally.

The released upstream 1.5.2 transport copies the authenticated client's headers into third-party upload requests and removes cookie/CSRF headers but not token-mode `Authorization`. Because this CLI uses token mode, implementation is blocked until the path used by the CLI proves Monarch credentials are never sent to the media host. Prefer an upstream fix and released dependency. A narrowly owned adapter transport is acceptable only with regression tests for destination-specific header stripping and with the maintenance tradeoff documented; command handlers must not call upstream private upload methods.

Make dry-run a required offline preview. It validates safe local metadata but performs no authentication lookup, transaction read, signed-parameter request, upload, or other network call. For execution, open the file once, validate the open descriptor as a regular readable non-empty file under the documented size cap, and read from that same descriptor to reduce path/symlink races. Derive the remote name from the basename unless an explicit sanitized filename is supplied. Extension/MIME checks are local policy based on filename and limited content checks; they do not guarantee server acceptance.

Do not automatically retry any stage after bytes or a registration request may have been dispatched. Use transaction detail for preflight existence and duplicate diagnostics and for post-failure/post-success verification. Keep receipt-inbox upload and follow-up transaction edits out of scope.

## Key Decisions

- **Credential isolation is a release blocker.** No Monarch authorization credential may reach a third-party upload host.
- **Dry-run is mandatory and offline.** Preview never requests signed parameters or reads file contents.
- **One open descriptor is validated and uploaded.** Validation must not inspect one path target and later upload another.
- **Multi-stage outcomes are honest.** The contract distinguishes asset upload from transaction registration and never implies rollback.

## Acceptance Criteria

- [ ] A user can attach one supported readable local file to one explicitly identified transaction.
- [ ] The command is classified `remote_mutation`, is blocked by default, and requires the shared per-invocation mutation authorization mechanism.
- [ ] Required dry-run performs no authentication lookup or network call and reports only target transaction ID, sanitized remote basename, local size, and locally inferred type.
- [ ] Execution opens the file once and rejects nonexistent, unreadable, non-regular, empty, over-limit, or unsupported inputs before authentication or any remote operation.
- [ ] Exact supported extensions/types, maximum size, filename length/character policy, symlink handling, and the limits of MIME/content validation are documented and tested.
- [ ] The local directory path and file contents never appear in output, diagnostics, logs, or the remote filename unless the user explicitly supplies an independently validated name.
- [ ] Requests to third-party upload hosts contain no Monarch `Authorization`, cookie, CSRF, session, or other credentials; a transport-level regression test inspects actual prepared/request headers.
- [ ] The required safe transport is supplied by a released upstream version or a documented public adapter boundary; command code does not depend directly on upstream private methods.
- [ ] Transaction existence is checked before upload, and a same-filename/size attachment is handled through a documented duplicate warning or explicit override rather than silently assumed equivalent.
- [ ] No stage is automatically retried after an upload or registration request may have been dispatched; stage-specific timeout/disconnect paths are classified as ambiguous with safe verification guidance.
- [ ] Cloud/media HTTP rejection and inner `addTransactionAttachment.errors` are sanitized and mapped to definitive structured failures rather than success.
- [ ] `mutation-outcome.v1` represents media-upload and transaction-registration effects distinctly enough to report success, orphaned-asset partial completion, definitive failure, and ambiguity without claiming rollback.
- [ ] Successful registration is verified through transaction detail; stable results include transaction ID, attachment ID and public ID when available, sanitized filename, and server-reported extension/size.
- [ ] Dependency metadata requires a release containing attachment upload (introduced in 1.2.0), satisfies the `mc-hszv` 1.5.2 floor, and is raised to the safe release if credential isolation lands upstream; clean-install compatibility is tested.
- [ ] Tests mock file, transaction, upload, and registration boundaries and cover authorization, offline dry-run, descriptor validation, header isolation, duplicate handling, every stage outcome, verification, and output modes.
- [ ] Receipt-inbox upload and follow-up transaction edits remain out of scope; no live financial API call is required by the default suite.
- [ ] Privacy/safety documentation and repository verification are complete.

