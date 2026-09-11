---
id: mc-87ez
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv, mc-2btg]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, transactions, tags, mutations, safety]
---
# Add safe transaction tag workflows

Support reusable transaction classification directly from the CLI. Users and automated workflows need to discover available tags, inspect existing assignments, and deliberately change them without accidentally replacing unrelated metadata. Tag writes alter financial records and therefore must build on the shared mutation authorization and execution contracts.

## Design

Treat tags as a transaction subresource. Provide read-only listing and assignment inspection plus explicit create, replace, and clear mutations. The released upstream client offers only complete-set replacement; incremental add/remove would require a non-atomic read-modify-write sequence that can overwrite concurrent changes. Defer add/remove until a conflict policy or upstream conditional-write mechanism exists.

Use distinct commands: `transactions tags list`, `transactions tags show TRANSACTION_ID`, `transactions tags create`, `transactions tags replace TRANSACTION_ID TAG_ID...`, and `transactions tags clear TRANSACTION_ID`. Replacement requires at least one tag ID; clearing is the only empty-set operation. Mutating invocations operate on one transaction at a time. Deduplicate requested IDs while preserving first-occurrence order, validate them against tag discovery before mutation, and compare the returned tag-ID set with the requested result.

Tag creation accepts a non-empty trimmed name and a six-digit `#RRGGBB` color; dashboard-palette restriction and name uniqueness are not claimed. Inspect payload-level GraphQL `errors` for both create and set operations instead of treating every returned dictionary as success.

Replace and clear are destructive full-set operations. They require the shared mutation authorization plus destructive confirmation or `--yes`, with deterministic non-interactive handling from `mc-2btg`. All mutations use the shared no-retry mutation executor and `mutation-outcome.v1` contract.

## Key Decisions

- **Incremental add/remove are deferred.** Preserving tags observed during a pre-read cannot protect concurrent assignments with the available API.
- **Replace is non-empty; clear is explicit.** An empty replacement cannot accidentally erase assignments.
- **One transaction per invocation.** Batch tag changes and their partial-outcome semantics are outside this ticket.
- **Server payload errors are failures.** HTTP/GraphQL transport success alone is insufficient.

## Acceptance Criteria

- [ ] Users can list all available tags and inspect tags assigned to a transaction without mutation authorization.
- [ ] Authorized users can create a tag using a non-empty trimmed name and locally validated `#[0-9A-Fa-f]{6}` color.
- [ ] Authorized users can replace the complete tag set for one transaction with one or more known tag IDs.
- [ ] Authorized users can clear all tags through a distinct explicit operation; empty replacement requests are rejected before mutation.
- [ ] Incremental add/remove and multi-transaction batch tagging are not exposed by this ticket.
- [ ] Duplicate requested IDs are removed deterministically in first-occurrence order; unknown IDs fail after read-only discovery and before mutation.
- [ ] Pre-validation/read failure prevents mutation, and payload-level create/set `errors` are mapped to definitive structured failures.
- [ ] Replace and clear are classified as destructive remote mutations, blocked by default, and require mutation authorization plus confirmation or `--yes` under deterministic non-interactive policy.
- [ ] Tag mutations execute through the shared mutation executor with no unsafe automatic retry after dispatch uncertainty.
- [ ] Mutation responses use `mutation-outcome.v1` with stable operation/entity identifiers and represent failed or ambiguous results honestly.
- [ ] The returned tag-ID set is compared with the expected set; mismatch exits as ambiguous/verification-required and supplies a tokenized transaction-detail verification command.
- [ ] Existing/already-equal tag sets produce a documented deterministic no-op success without making unsupported atomicity claims.
- [ ] Unit/CLI tests cover reads, creation, replacement, clearing, duplicate/unknown IDs, authorization, confirmation, non-interactive behavior, payload errors, verification mismatch, transport ambiguity, and output modes.
- [ ] User-facing safety and concurrent-modification limitation documentation is complete and repository verification passes.

