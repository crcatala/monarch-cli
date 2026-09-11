---
id: mc-hp7w
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv, mc-2btg]
links: []
created: 2026-09-11T01:23:21Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, transactions, splits, mutations, safety]
---
# Add safe transaction split workflows

Allow users to inspect and deliberately change how a transaction is allocated across categories or merchants. Split replacement can materially alter reporting and budgets, and malformed totals can leave a transaction in an unintended state, so this workflow needs focused validation and the shared mutation safety contracts.

## Design

Treat splits as a transaction subresource with `transactions splits show TRANSACTION_ID`, `transactions splits replace TRANSACTION_ID`, and `transactions splits clear TRANSACTION_ID`. The released API supports complete-set replacement only; merge and per-split editing are not offered. Clearing sends the one canonical empty-list wire form.

Accept exactly one payload source per invocation—inline JSON or a bounded readable JSON file—with items containing only `merchantName`, `amount`, and `categoryId`. Notes, tags, goals, split IDs, and merchant IDs are not accepted because the released mutation contract does not document them. Repeated merchant names may be legitimate; reject only byte-for-byte-equivalent duplicate normalized records as an explicit CLI policy.

Before replacement, read the parent transaction amount and validate structure and totals using `Decimal` parsed from JSON number text. Define the supported decimal precision and require the signed normalized sum to equal the signed parent amount at that precision; do not use binary-float equality or an unexplained tolerance. The server remains authoritative because the parent may change between read and write.

Inspect payload-level `updateTransactionSplit.errors` as definitive failures. Execute through the shared no-retry mutation boundary and verify the resulting split set with `get_transaction_splits`. Replace and clear discard existing allocation state and therefore require destructive confirmation or `--yes` in addition to mutation authorization.

## Key Decisions

- **Only replace and clear.** Merge semantics do not exist upstream.
- **Narrow v1 schema.** The mutation accepts only documented merchant name, amount, and category ID fields.
- **Decimal total validation.** Financial equality is checked at a documented precision, with the server still authoritative.
- **One transaction per invocation.** Multi-transaction workflows are outside scope.

## Acceptance Criteria

- [ ] Users can inspect the parent transaction and its current split rows without mutation authorization.
- [ ] Authorized users can replace all splits for one transaction using the documented JSON array from exactly one of inline input or a bounded readable file.
- [ ] Authorized users can clear all splits through a distinct explicit operation using an empty-list upstream payload.
- [ ] Merge, per-split editing, split notes/tags/goals, and multi-transaction updates are not exposed.
- [ ] Each replacement record contains exactly non-empty `merchantName`, finite decimal `amount`, and non-empty opaque-string `categoryId`; unsupported fields fail before mutation.
- [ ] Exact duplicate normalized records are rejected as CLI policy, while repeated merchant names with otherwise different allocations remain valid.
- [ ] The invocation reads the parent amount before mutation and rejects totals that do not equal the signed parent amount at the documented decimal precision.
- [ ] Precision, maximum decimal places, expense/income sign conventions, zero-amount behavior, minimum split count, and input-size limits are documented and tested.
- [ ] Payload-level `updateTransactionSplit.errors` are mapped to definitive structured failures and never reported as success.
- [ ] Replace and clear are destructive remote mutations, blocked by default, and require mutation authorization plus confirmation or `--yes` under deterministic non-interactive policy.
- [ ] Split writes use the shared mutation executor with no automatic retry after dispatch uncertainty and return `mutation-outcome.v1` using stable operation/entity identifiers.
- [ ] A successful response is verified against a read of the resulting splits; mismatch or uncertain transport produces exit code `4` and actionable tokenized verification guidance.
- [ ] Server-specific unsupported cases such as pending transactions or clearing an unsplit transaction are surfaced honestly without fabricated local semantics.
- [ ] Unit/CLI tests cover inspection, both input sources, source conflicts, validation, authorization, confirmation, replacement, clearing, payload rejection, ambiguity, verification, and output modes.
- [ ] A documented opt-in live/manual verification checklist covers upstream split edge behavior; user-facing safety documentation and repository verification are complete.

