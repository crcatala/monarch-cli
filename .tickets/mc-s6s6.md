---
id: mc-s6s6
status: closed
deps: [mc-vv11, mc-hu2c]
links: [mc-hu2c]
created: 2026-09-19T01:19:38Z
type: task
priority: 1
assignee: cc-vps
parent: mc-qv0q
tags: [cli, validation, safety, ux, automation]
---
# Harden CLI validation and flag interaction semantics

The command surface has edge cases where invalid or incompatible flags are not rejected early, or where help/error text does not match the actual option names. These are small changes individually but important for safe automation and predictable failure behavior.

## Design

Prefer a small number of central rules over per-command special cases. Validation runs at the shared command/service boundary, before mutation authorization can lead to authentication, client creation, or any prompt. Keep the existing structured validation error contract (`INVALID_INPUT`, exit 2).

Rules:

- **Validation order.** Input validation precedes mutation authorization; authorization always precedes authentication lookup, client creation, and prompts.
- **One strict date parser.** Every explicit date option uses `core.dates.parse_iso_date` (`YYYY-MM-DD` only). Remove the duplicate loose `_parse_date` in `transactions.py`; invalid dates must raise the structured usage error, never `UNKNOWN`/"Unexpected error".
- **Finite numbers only.** Transaction update amounts reject NaN, infinity, and other non-finite values while allowing valid positive, negative, and zero amounts. Split amounts already validate finiteness; reuse the same approach so dry-run output cannot contain `NaN`/`Infinity` JSON literals.
- **Validated numeric bounds.** `transactions batch-update --max-concurrency` accepts integers 1 through 16 (default 4) and `--timeout` accepts integers >= 1; invalid values fail before authentication or mutation. The concurrency bound is a local safety cap with no upstream guarantee. Zero must be rejected explicitly: `asyncio.Semaphore(0)` currently hangs the command, and negative values currently surface an internal exception as `UNKNOWN`.
- **`--raw` never silently ignores normalized-only options.** Options that only shape or compute normalized output are rejected with a structured incompatibility error when `--raw` is selected. Known violations: `institutions list --raw --include-deleted` and `investments holdings --raw --aggregate`.
- **`--quiet` never silently discards records.** Quiet output errors when records exist but no id can be extracted, instead of printing nothing. Mutation and preview output is exempt because it is never rendered through the quiet path (owned by `mc-hu2c`).

Correct the stale keyring guidance from `--backend=file` to the actual `--storage=file` option. Clarify `--yes` as confirmation bypass only; it never grants mutation authorization. Update help text for cross-field requirements in coordination with the existing help audit ticket `mc-4z49`.

## Acceptance Criteria

- [ ] `transactions batch-update --max-concurrency` accepts only integers 1 through 16 (default 4) and rejects 0, negatives, and out-of-range values with a structured pre-execution error before authentication or mutation.
- [ ] A zero or negative `--max-concurrency` can no longer hang the process or surface an internal `UNKNOWN` error.
- [ ] `transactions update --date` and `transactions list --start/--end` use the shared strict `YYYY-MM-DD` validator; the duplicate loose parser is removed, and compact forms such as `20240115` and `2024-1-5` fail with `INVALID_INPUT`/exit 2.
- [ ] Transaction update amounts reject NaN, infinity, and other non-finite values while allowing valid positive, negative, and zero amounts; non-finite values can no longer produce invalid JSON in dry-run output.
- [ ] Global `--timeout` rejects values below 1 before any API call.
- [ ] `institutions list --raw --include-deleted` and `investments holdings --raw --aggregate` fail with a structured incompatibility error rather than silently ignoring the normalized-only option, and the rule is documented for future commands.
- [ ] `--quiet` errors when records exist but no id can be extracted instead of printing nothing; mutation and preview output is never silenced by `--quiet`.
- [ ] Keyring-unavailable errors consistently recommend `--storage=file` or `MONARCH_TOKEN`; no stale `--backend=file` guidance remains.
- [ ] Global `--yes` help and relevant mutation help explain that it skips confirmation only and never authorizes a remote write.
- [ ] Cross-field preconditions for update, batch-update, split input, and tag creation are described accurately in help in coordination with `mc-4z49`.
- [ ] Tests cover early validation, no client lookup/no mutation on invalid input, the raw/incompatibility behavior, quiet-without-ids behavior, and corrected error guidance.
- [ ] Repository verification passes.
