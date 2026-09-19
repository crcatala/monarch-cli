---
id: mc-46gq
status: open
deps: []
links: []
parent: mc-qv0q  # Major-release CLI UX consistency and safety hardening
created: 2026-09-19T00:57:28Z
type: feature
priority: 1
assignee: cc-vps
tags: [tags, transactions, cli, breaking-change, ux]
---
# Redesign transaction tag assignment UX and add additive tag operations

The current transaction-tag mutation UX relies on positional arguments such as `transactions tags replace TRANSACTION_ID TAG_ID...`, which makes it easy to reverse identifiers and is less discoverable. The current implementation already supports a list of tag IDs and calls the upstream `setTransactionTags` mutation, which accepts a tag ID array and replaces the complete assignment. However, the CLI exposes no name-based resolution and no additive operation.

For the next major release, intentionally make a breaking CLI change: remove the positional tag-assignment interface and use explicit required options. Support assigning multiple tags by repeated options, resolve exact tag names through the existing tag-discovery call, add a `set` alias for complete replacement, and add a safe additive `add` workflow that preserves existing tags while avoiding duplicate assignments.

## Design

## Proposed CLI surface

Use explicit options for all transaction-targeted tag mutations; do not retain positional compatibility:

```text
transactions tags replace --transaction-id TXN_ID --tag-id TAG_ID [--tag-id TAG_ID ...] [--tag-name NAME ...]
transactions tags set     --transaction-id TXN_ID --tag-id TAG_ID [--tag-id TAG_ID ...] [--tag-name NAME ...]
transactions tags add     --transaction-id TXN_ID --tag-id TAG_ID [--tag-id TAG_ID ...] [--tag-name NAME ...]
transactions tags clear   --transaction-id TXN_ID
```

`--tag-id` and `--tag-name` are repeatable and may be mixed. Require at least one tag reference for replace/set/add. Do not require comma-separated `--tags` parsing; repeatable typed options avoid ambiguity with tag names containing commas and are easier to script. If a compact combined option is added, it must have the same exact-resolution and duplicate behavior.

`set` is an alias of `replace`, not a separate remote operation. Keep its mutation outcome operation identifier compatible with `transactions.tags.replace`. `add` is a new CLI operation and should have an explicit `transactions.tags.add` operation identifier.

## Resolution and API behavior

The released `monarchmoneycommunity` client exposes `get_transaction_tags()`, `get_transaction_details()`, and `set_transaction_tags(transaction_id, tag_ids)`. The latter sends `setTransactionTags` with `tagIds`, replaces the entire tag set, and accepts an empty list for clearing; there is no atomic add-tag endpoint.

Reuse one tag-discovery response to resolve and validate all inputs. Tag names must match exactly (case-sensitive after only safe CLI whitespace trimming). A missing name/ID is a pre-mutation validation error. Multiple tags with the same exact name must produce an ambiguity error listing candidate IDs rather than guessing. Deduplicate resolved IDs while preserving first-seen order.

`replace`/`set` send exactly the resolved tag set. `add` reads the current assignment, computes current IDs union requested IDs, preserves existing tags and their order, skips the mutation as a deterministic no-op when nothing is new, and otherwise calls the same full-set API once. Document and test that `add` is read-modify-write and is not atomic against concurrent tag changes because the upstream API has no conditional-write/add endpoint.

Retain existing authorization, confirmation, read-before-write validation, response verification, mutation-outcome handling, ambiguity exit behavior, and no-automatic-retry policy. Add-result data should make the additive behavior observable, including final tag IDs, added IDs, skipped/already-present IDs, and `no_op`.

## Acceptance Criteria

- [ ] `replace`, `set`, `add`, and `clear` use a required `--transaction-id` option; positional transaction/tag arguments are removed for the next major release.
- [ ] `replace` and `set` accept multiple tag references through repeatable `--tag-id` and/or `--tag-name` options, require at least one reference, and allow the two option types to be mixed.
- [ ] `set` is a CLI alias for `replace` with identical validation, confirmation, API behavior, output, verification, and stable mutation operation identifier.
- [ ] `add` accepts the same repeatable tag-reference options and preserves all existing transaction tags while adding only missing tags.
- [ ] Tag IDs are validated against the discovered household tag collection before any mutation; duplicate IDs/references are deduplicated in first-seen order.
- [ ] Tag names resolve through the existing tag-discovery response using exact matching; unknown names and ambiguous duplicate-name matches fail with actionable structured validation errors before mutation.
- [ ] Name resolution does not introduce an unnecessary additional discovery request when the existing workflow already fetched the complete tag collection.
- [ ] `add` performs a read-modify-write using the existing `set_transaction_tags` full-set mutation, makes no mutation for an already-satisfied request, and reports final IDs plus added/skipped IDs and no-op state.
- [ ] The implementation does not claim atomic additive semantics; concurrency/read-modify-write limitations and safe verification guidance are documented.
- [ ] All remote tag mutations remain blocked unless `--allow-mutations` is supplied before the command path; destructive confirmation and `--yes` behavior remain consistent with current tag replacement/clear workflows.
- [ ] `replace`, `set`, `add`, and `clear` preserve the shared `mutation-outcome.v1` contract, including ambiguous/verification-required outcomes and no automatic retry after a dispatched write.
- [ ] The operation taxonomy and mutation outcome mapping include the new add operation without changing the existing replace operation contract.
- [ ] Command help and README documentation show explicit-option, multi-tag, ID-based, name-based, mixed, set-alias, add, clear, and mutation-authorization examples.
- [ ] Unit/CLI tests cover parsing, required flags, multiple IDs/names, mixed references, exact matching, unknown/ambiguous names, deduplication, replace/set equivalence, add union/no-op behavior, API call payloads, confirmation, authorization, malformed reads, verification mismatch, and ambiguous writes.
- [ ] Repository verification passes.

