---
id: mc-ks6s
status: open
deps: []
links: [mc-61tf]
created: 2026-09-19T19:11:02Z
type: task
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [contract, schema, read-only]
---
# Unify and type review-attribution normalization across read/write paths

Follow-up from mc-61tf (PR #90), which added reviewed_at/reviewed_by_user to normalized transaction detail. Two review-attribution normalizers now exist independently: _reviewed_by_user in transformers/transactions.py (read path) and _normalize_user in commands/transaction_review.py (write path). Both pass upstream values through untyped: reviewed_at uses nested_get (literal passthrough) and reviewed_by_user.id/name use dict .get() without type checks, while the published transaction-detail:v1 schema declares reviewed_at as string|null and reviewed_by_user.id/name as string|null.

Why it matters: upstream drift (for example a timestamp or identifier returned as a number/object/list) would emit schema-invalid normalized detail with no error. The two copies agree today but can silently diverge if either side changes, recreating the read/write inconsistency mc-61tf set out to remove.

What it solves: one shared typed review-attribution normalizer, consumed by both the read transformer and the review-command write path, that coerces non-string values to null and guarantees output validates against transaction-detail:v1.

## Design

Keep the review-mutation wire input unchanged; this is normalization only. Empty-object reviewedByUser -> {id: null, name: null} is deliberate read/write parity and must be preserved (changing it is out of scope). Consider whether ownership_overridden_at deserves the same typed treatment, but treat that as a separate decision. Do not import a private command helper into the transformer layer; place the shared helper in a neutral location (for example transformers/ or a small shared review module) so the dependency direction stays clean.

## Acceptance Criteria

One shared helper normalizes reviewedAt/reviewedByUser (and its {id, name} shape) for both transform_transaction_detail and the transaction_review read path.
Non-string reviewedAt, id, and name coerce to null; resulting output always validates against transaction-detail:v1.
Tests pin the shared behavior for both paths and for malformed/drifted upstream shapes (number/object/list instead of string).
No review-mutation wire-input change; empty-object reviewedByUser semantics preserved.


## Notes

**2026-09-19T19:11:04Z**

Priority is intentionally low (P3). There is no observed failure and no user-visible impact today: both normalizers agree and owned upstream values are strings in practice. This is contract-hygiene/robustness work, not a correctness bug, so it can wait behind functional tickets. Filed from the mc-61tf review rather than expanding that contract PR.
