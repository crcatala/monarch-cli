---
id: mc-s6s6
status: open
deps: []
links: []
created: 2026-09-19T01:19:38Z
type: task
priority: 1
assignee: cc-vps
parent: mc-qv0q
tags: [cli, validation, safety, ux, automation]
---
# Harden CLI validation and flag interaction semantics

The command surface has a handful of edge cases where invalid or incompatible flags are not rejected early, or where help/error text does not match the actual option names. These are small changes individually but important for safe automation and predictable failure behavior.

## Design

Harden validation at the shared command/service boundaries. Reject invalid concurrency before authentication or mutation, run transaction update dates through the shared strict ISO-date validator, and reject non-finite amounts. Make incompatible raw/projection options explicit rather than silently ignoring a flag. Keep the existing structured validation error contract.

Correct the stale keyring guidance from `--backend=file` to the actual `--storage=file` option. Clarify `--yes` as confirmation bypass only; it never grants mutation authorization. Update help text for cross-field requirements in coordination with the existing help audit ticket `mc-4z49`.

## Acceptance Criteria

- [ ] `transactions batch-update --max-concurrency` accepts only integers in the documented safe range 1 through 16, with default 4, and rejects invalid values before authentication or mutation.
- [ ] `transactions update --date` uses the shared strict `YYYY-MM-DD` validator before authentication or mutation.
- [ ] Transaction update amounts reject NaN, infinity, and other non-finite values while allowing valid positive, negative, and zero amounts.
- [ ] `institutions list --raw --include-deleted` has an explicit deterministic behavior; preferably it fails with a structured incompatibility error rather than silently ignoring `--include-deleted`.
- [ ] Keyring-unavailable errors consistently recommend `--storage=file` or `MONARCH_TOKEN`; no stale `--backend=file` guidance remains.
- [ ] Global `--yes` help and relevant mutation help explain that it skips confirmation only and never authorizes a remote write.
- [ ] Cross-field preconditions for update, batch-update, split input, and tag creation are described accurately in help in coordination with `mc-4z49`.
- [ ] Tests cover early validation, no client lookup/no mutation on invalid input, raw/projection behavior, and corrected error guidance.
- [ ] Repository verification passes.

