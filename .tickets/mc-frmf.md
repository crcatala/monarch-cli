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

Allow a receipt to be submitted to the household receipt inbox when the target transaction is not yet known. This capture-first workflow is distinct from attaching a document to an existing transaction and may trigger asynchronous categorization or matching.

Receipt contents are sensitive, and the verified upstream workflow has multiple remote stages with no supported post-start status lookup. The CLI must validate locally before any remote action, avoid unsafe retries, and report only what it can actually observe.

## Design

Model inbox submission as its own three-stage remote workflow: create a retail-sync session, upload one file to the Monarch retail-sync endpoint, then start processing. Reuse the shared file-validation primitives established by `mc-2v9a`, while keeping transaction attachment and receipt-sync result semantics separate. The dependency on `mc-2v9a` is intentionally conservative even though its Cloudinary-specific transport is not used here.

Open and validate the file before authentication or creation of the retail-sync session. Execution opens the file once, validates that descriptor as a readable regular non-empty file under the documented cap, and uploads from the same descriptor. Derive a sanitized remote basename and never expose a local directory path or file contents. Required dry-run performs metadata validation only and makes no authentication or network call.

The verified 1.5.2 client returns the retail-sync identity and status observed when processing starts, but provides no public method to retrieve that sync later or determine whether categorization/matching completed. Stable output therefore distinguishes local validation, session creation, file transfer, and processing-start acceptance, and reports only the returned initial sync status. Later processing or matching is `unknown`; polling and inbox inspection are separate future work.

No remote stage is automatically retried after its request may have been dispatched. Every invocation creates a new sync/order identity, so an ambiguous failure can produce a duplicate if the user reruns it. Recovery guidance instructs the user to inspect the receipt inbox manually rather than implying that retry is safe.

## Key Decisions

- **Three explicit stages.** Following `mc-ik8o`, attempted session creation, file transfer, and processing start are ordered effect items with separate outcomes.
- **Initial status only.** This ticket does not poll or claim completed categorization/matching.
- **Validation before all remote work.** Invalid input cannot create an orphan retail-sync session.
- **Mandatory offline dry-run.** Preview does not authenticate, read file contents, or call the network.
- **No automatic retry.** Ambiguous receipt uploads require manual inbox inspection.
- **Conservative prerequisite.** Reuse `mc-2v9a` file primitives even though receipt upload does not use its Cloudinary transport.

## Acceptance Criteria

- [ ] A user can submit one supported readable receipt file without specifying a transaction ID.
- [ ] The command and output clearly distinguish inbox submission from attaching a file to an existing transaction.
- [ ] The operation is classified `remote_mutation`, blocked by default, and requires shared per-invocation mutation authorization.
- [ ] Required dry-run validates safe metadata without authentication lookup, client creation, file-content reads, retail-sync creation, upload, or any network call.
- [ ] Execution opens the file once and rejects nonexistent, unreadable, non-regular, empty, unsupported, policy-exceeding, and disallowed-symlink inputs before authentication or any remote mutation.
- [ ] Supported extensions/types, size cap, basename length/character policy, symlink behavior, and limits of filename/MIME validation are documented and tested.
- [ ] The same validated descriptor supplies uploaded bytes, reducing path/symlink races.
- [ ] Output and diagnostics never include receipt contents, credentials, or unintended local directory information.
- [ ] Following `mc-ik8o`, each attempted or observable remote stage is an ordered effect item in `mutation-outcome.v1`; mixed outcomes report partial completion without a command-specific envelope or rollback claim.
- [ ] Stable success output includes sanitized filename metadata, size, returned retail-sync ID, and the status observed at processing start.
- [ ] Output explicitly states that later processing, categorization, and transaction matching are unknown because the supported client has no status-read capability.
- [ ] No polling, completed/matched claim, or synthetic final status is introduced by this ticket.
- [ ] No remote stage is automatically retried after dispatch may have occurred; ambiguous outcomes warn that rerunning may duplicate the receipt and recommend manual inbox inspection.
- [ ] Tests cover authorization, offline dry-run, descriptor validation, every stage's success/failure/ambiguous paths, partial completion, redaction, duplicate-risk guidance, and output modes without live financial API access.
- [ ] Project metadata requires the verified upstream floor exposing `upload_receipt_to_inbox`; client-interface and clean-install tests enforce it.
- [ ] Privacy, safety, status-limit, and recovery documentation is complete and repository verification passes.
