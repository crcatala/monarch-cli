---
id: mc-46gq
status: in_progress
deps: []
links: []
parent: mc-qv0q
created: 2026-09-19T00:57:28Z
type: feature
priority: 1
assignee: cc-vps
tags: [tags, transactions, cli, breaking-change, ux]
---
# Redesign transaction tag assignment UX and add additive tag operations

The current transaction-tag mutation UX relies on positional arguments such as `transactions tags replace TRANSACTION_ID TAG_ID...`, which makes it easy to reverse identifiers and is less discoverable. The current implementation already supports a list of tag IDs and calls the upstream `setTransactionTags` mutation, which accepts a tag ID array and replaces the complete assignment. However, the CLI exposes no name-based resolution and no additive operation.

For the next breaking release, intentionally make a breaking CLI change: remove the positional tag-assignment interface and use explicit required options. Support assigning multiple tags by repeated options, resolve exact tag names through the existing tag-discovery call, and add a safe additive `add` workflow that preserves existing tags while avoiding duplicate assignments.

## Design

## Proposed CLI surface

Use explicit options for all transaction-targeted tag mutations; do not retain positional compatibility or aliases:

```text
transactions tags replace --transaction-id TXN_ID --tag-id TAG_ID [--tag-id TAG_ID ...] [--tag-name NAME ...]
transactions tags add     --transaction-id TXN_ID --tag-id TAG_ID [--tag-id TAG_ID ...] [--tag-name NAME ...]
transactions tags clear   --transaction-id TXN_ID
```

`--tag-id` and `--tag-name` are repeatable and may be mixed. Require at least one tag reference for replace/add. Do not require comma-separated `--tags` parsing; repeatable typed options avoid ambiguity with tag names containing commas and are easier to script.

One verb per operation: `replace` keeps its name and no `set` alias is added. An alias would add a second inventory entry, help page, and test surface for the same remote operation, contradicting the epic's one-verb/no-shim policy. The stable mutation outcome operation identifier remains `transactions.tags.replace`; `add` is a new CLI operation registered as `transactions.tags.add`.

## Resolution and API behavior

The released `monarchmoneycommunity` client exposes `get_transaction_tags()`, `get_transaction_details()`, and `set_transaction_tags(transaction_id, tag_ids)`. `get_transaction_tags()` returns the household tag collection (`householdTransactionTags`), and `get_transaction_details()` returns the transaction's current tags with IDs, names, colors, and order. `set_transaction_tags` sends `setTransactionTags` with `tagIds`, replaces the entire tag set, and accepts an empty list for clearing; there is no atomic add-tag endpoint.

Reuse one tag-discovery response to resolve and validate all inputs; do not issue a second discovery request when the workflow already fetched the complete collection. Tag names match exactly and case-sensitively: apply only whitespace trimming to the CLI input, and compare against the upstream name exactly as returned (do not normalize upstream names). A missing name/ID is a pre-mutation validation error. Multiple tags with the same exact name must produce an ambiguity error listing candidate IDs rather than guessing. Deduplicate resolved IDs while preserving first-seen order.

`replace` sends exactly the resolved tag set. `add` reads the current assignment, computes current IDs union requested IDs, preserves existing tags and their order, skips the mutation as a deterministic no-op when nothing is new, and otherwise calls the same full-set API once. Current tag IDs that are no longer present in household discovery are preserved verbatim in the union; a write whose verified response drops them is reported as a verification-mismatch/ambiguous outcome, never silently repaired. Document and test that `add` is read-modify-write and is not atomic against concurrent tag changes because the upstream API has no conditional-write/add endpoint.

Retain existing authorization, confirmation, read-before-write validation, response verification, mutation-outcome handling, ambiguity exit behavior, and no-automatic-retry policy. Add-result data should make the additive behavior observable, including final tag IDs, added IDs, skipped/already-present IDs, and `no_op`.

Extract the duplicated command-layer mutation primitives shared with `transaction_splits.py` (destructive confirmation, transaction-ID validation, payload container/error parsing, and object coercion) into one small shared command helper module used by both commands. Do not build a generic mutation pipeline.

README currently guarantees that the CLI "never exposes incremental add/remove or batch tagging"; the `add` operation reverses half of that guarantee and the README/migration notes must be updated explicitly.

## Acceptance Criteria

- [ ] `replace`, `add`, and `clear` use a required `--transaction-id` option; positional transaction/tag arguments are removed for the next breaking release.
- [ ] `replace` and `add` accept multiple tag references through repeatable `--tag-id` and/or `--tag-name` options, require at least one reference, and allow the two option types to be mixed.
- [ ] No `set` alias (or other compatibility alias) is added; `replace` remains the single complete-set verb and its outcome operation identifier stays `transactions.tags.replace`.
- [ ] `add` accepts the same repeatable tag-reference options and preserves all existing transaction tags while adding only missing tags.
- [ ] Tag IDs are validated against the discovered household tag collection before any mutation; duplicate IDs/references are deduplicated in first-seen order.
- [ ] Tag names resolve through the existing tag-discovery response using exact, case-sensitive matching with CLI-input-only whitespace trimming; unknown names and ambiguous duplicate-name matches fail with actionable structured validation errors before mutation.
- [ ] `add` preserves current tag IDs that are absent from household discovery verbatim in the union, and a response that drops them is reported as a verification-mismatch/ambiguous outcome.
- [ ] `add` performs a read-modify-write using the existing `set_transaction_tags` full-set mutation, makes no mutation for an already-satisfied request, and reports final IDs plus added/skipped IDs and no-op state.
- [ ] The implementation does not claim atomic additive semantics; concurrency/read-modify-write limitations and safe verification guidance are documented.
- [ ] All remote tag mutations remain blocked unless `--allow-mutations` is supplied before the command path; destructive confirmation and `--yes` behavior remain consistent with current tag replacement/clear workflows.
- [ ] `replace`, `add`, and `clear` preserve the shared `mutation-outcome.v1` contract, including ambiguous/verification-required outcomes and no automatic retry after a dispatched write.
- [ ] The operation taxonomy, command inventory, and mutation outcome/retry mappings include `transactions tags add` without changing the existing replace contract.
- [ ] The duplicated mutation primitives shared with the splits command live in one shared command helper module; no generic mutation pipeline is introduced.
- [ ] Command help and README documentation show explicit-option, multi-tag, ID-based, name-based, mixed, add, clear, and mutation-authorization examples, and no longer state that incremental tag additions are never exposed.
- [ ] Unit/CLI tests cover parsing, required flags, multiple IDs/names, mixed references, exact matching, unknown/ambiguous names, deduplication, add union/no-op behavior, stale current IDs, API call payloads, confirmation, authorization, malformed reads, verification mismatch, and ambiguous writes.
- [ ] Repository verification passes.
