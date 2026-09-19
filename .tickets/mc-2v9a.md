---
id: mc-2v9a
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv, mc-sr92]
links: [mc-sr92]
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

Add `transactions attachments add --transaction-id TXN_ID --file PATH` as a three-stage remote workflow: obtain transaction-specific signed upload parameters, upload the asset to the third-party media host, then register that asset on the transaction. Each stage has distinct definitive, ambiguous, and partial outcomes; successful media upload followed by failed registration may leave an orphaned asset, while a lost registration response may leave an attachment that exists remotely but is not yet known locally. Target selection follows the `mc-qv0q` mutation convention: an explicit required `--transaction-id` option plus a `--file` option, never positional arguments.

Credential-safe third-party transport is owned by prerequisite `mc-sr92`. This ticket consumes that public adapter boundary and does not reproduce its header-isolation, redirect, or upstream-version logic. The workflow must not call `MonarchMoney.upload_attachment()` directly: the existing public method hides the three stages and currently owns the unsafe third-party transport. The attachment gateway should keep authenticated Monarch operations (signed-parameter acquisition and attachment registration) conceptually separate from the safe media-upload transport. If the released client does not expose those authenticated stages through a suitable public interface, any narrow compatibility implementation belongs behind the adapter boundary with explicit query/version assumptions and tests; it must not be command-local or call upstream private methods from commands/services.

The v1 command is `transactions attachments add --transaction-id TXN_ID --file PATH`, with an optional `--filename NAME` override. Without an override, the sanitized basename of `PATH` is used. Arbitrary filenames, local directory paths, and silent path-derived metadata are never sent to the remote service or exposed in output.

Make dry-run a required offline preview. It validates safe local metadata but performs no authentication lookup, transaction read, signed-parameter request, upload, or other network call. For execution, open the file once, validate the open descriptor as a regular readable non-empty file under the documented size cap, and read from that same descriptor to reduce path/symlink races. Extension/MIME checks are local policy based on filename and limited content checks; they do not guarantee server acceptance.

Do not automatically retry any stage after bytes or a registration request may have been dispatched. Use an exact transaction-detail read, without silently redirecting a pending ID, to verify the requested target before upload and for post-failure/post-success verification. An explicit attachment request may create another attachment with the same filename or size; filename/size heuristics do not establish duplicate identity, and the workflow makes no cleanup/rollback claim for an orphaned media asset. Keep receipt-inbox upload and follow-up transaction edits—including `--notes` convenience updates—out of scope.

## Key Decisions

- **Credential isolation is a prerequisite.** `mc-sr92` must provide the public safe transport before this workflow can ship.
- **Dry-run is mandatory and offline.** Preview never requests signed parameters or reads file contents.
- **One open descriptor is validated and uploaded.** Validation must not inspect one path target and later upload another.
- **Multi-stage outcomes are honest.** A signed-parameter failure before any mutation uses the structured error contract; following `mc-ik8o`, attempted media upload and transaction registration are ordered effect items and never imply rollback.
- **No monolithic upload shortcut.** The workflow must retain stage boundaries rather than treating a single upstream `upload_attachment()` call as an atomic operation.
- **Exact target verification.** The requested transaction ID is checked without silent pending-to-posted redirection; any supported redirect behavior must be an explicit, documented product decision rather than an invisible change of target.
- **Stable operation identity.** The workflow uses the namespaced operation `transactions.attachments.add` and the existing generic mutation envelope; it does not introduce an attachment-specific top-level response shape.

## Acceptance Criteria

- [ ] A user can attach one supported readable local file to one explicitly identified transaction.
- [ ] The command selects the target with a required `--transaction-id` option and the file with a `--file` option, with no positional arguments.
- [ ] The command is classified `remote_mutation`, is blocked by default, and requires the shared per-invocation mutation authorization mechanism.
- [ ] Required dry-run performs no authentication lookup or network call and reports only target transaction ID, sanitized remote basename, local size, and locally inferred type.
- [ ] Execution opens the file once and rejects nonexistent, unreadable, non-regular, empty, over-limit, or unsupported inputs before authentication or any remote operation.
- [ ] Exact supported extensions/types, maximum size, filename length/character policy, symlink handling, and the limits of MIME/content validation are documented and tested; `--filename`, if supplied, is validated by the same policy as the derived basename.
- [ ] The local directory path and file contents never appear in output, diagnostics, logs, or the remote filename unless the user explicitly supplies an independently validated name.
- [ ] Signed upload parameters, third-party response bodies, and other sensitive transport data never appear in output, diagnostics, logs, or mutation error details.
- [ ] The command uses the credential-safe public upload adapter from completed prerequisite `mc-sr92`; no command/service calls `MonarchMoney.upload_attachment()` directly, and the implementation contains no ticket-local header workaround or upstream-private-method dependency.
- [ ] The workflow uses stable operation identity `transactions.attachments.add` and documents the stable effect entity/identity mapping used for media upload, registration, ambiguity, and partial completion under `mutation-outcome.v1`; the media stage uses its best-known public upload identity and the registration stage uses the returned Monarch attachment identity when available.
- [ ] Exact transaction existence and identity are checked before upload without silently redirecting a pending target; the workflow does not claim that filename/size matching can identify or prevent duplicate attachments.
- [ ] Successful registration is verified by returned attachment identity (`id`/`publicId` when available), not by filename or size alone; failed verification does not claim success or rollback.
- [ ] No stage is automatically retried after an upload or registration request may have been dispatched; stage-specific timeout/disconnect paths are classified as ambiguous with safe verification guidance.
- [ ] Cloud/media HTTP rejection and inner `addTransactionAttachment.errors` are sanitized and mapped to definitive structured failures rather than success.
- [ ] A signed-parameter failure before mutation uses the structured error contract; following `mc-ik8o`, each attempted or observable state-changing stage is an ordered effect item in `mutation-outcome.v1`, and mixed outcomes report orphaned-asset partial completion without a command-specific envelope or rollback claim.
- [ ] Successful registration is verified through transaction detail; stable results include transaction ID, attachment ID and public ID when available, sanitized filename, and server-reported extension/size.
- [ ] Dependency metadata satisfies the `mc-hszv` 1.5.2 floor and the transport compatibility contract selected by `mc-sr92`; clean-install compatibility is tested.
- [ ] Tests mock file, transaction, upload, and registration boundaries and cover authorization, offline dry-run, descriptor validation, repeated explicit uploads, every stage outcome, verification, and output modes.
- [ ] Receipt-inbox upload and follow-up transaction edits remain out of scope; no live financial API call is required by the default suite.
- [ ] Privacy/safety documentation and repository verification are complete.

