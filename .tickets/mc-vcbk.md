---
id: mc-vcbk
status: open
deps: [mc-3437, mc-cpzi]
links: []
created: 2026-09-11T01:47:48Z
type: task
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p3, testing, live, contracts, read-only]
---
# Add an opt-in live API contract smoke suite

Detect drift between mocked assumptions and the authenticated service before releases. Unit tests can verify local code while missing renamed fields, changed nullability, unsupported filters, or altered response envelopes. A small, deliberately invoked live suite provides release evidence without placing credentials or financial data in CI.

## Design

Build on and finish the local-only infrastructure in `mc-3437`; do not create a second runner. Formalize a read-only subset of the existing live tests and validate response shape, published schemas, normalization, and stable invariants rather than household-specific values.

`MONARCH_LIVE_TESTS=1` enables only the read-only contract smoke suite. Existing live mutation tests must be retired or moved behind a distinct, stronger opt-in such as `MONARCH_LIVE_MUTATION_TESTS=1`; the read-only release check must never select them. Any retained mutation tests also require explicit `--allow-mutations` after `mc-k48z` and are not part of this ticket's release evidence. Mutation and split-workflow contract testing remains out of scope pending a disposable-fixture design.

The initial matrix covers the established critical surfaces: authentication ping/status, bounded accounts list, bounded transactions list, categories list, budgets list, and cashflow summary. Holdings/reporting paths are added only when their CLI contracts exist and are separately declared in the matrix. Use subprocess CLI execution for release realism and published schemas from `mc-cpzi` where available.

Set explicit per-command record/page limits, a total request budget, timeout, and inter-request delay. The suite performs no refresh, login replacement, upload, transaction/account edit, or other operation classified as anything but read-only. Diagnostics identify the contract and invariant that failed while redacting credentials and returned financial values.

## Key Decisions

- **One live runner.** Extend `mc-3437` rather than introducing parallel infrastructure.
- **Read-only opt-in is isolated.** `MONARCH_LIVE_TESTS` cannot select mutation tests.
- **Concrete bounded matrix.** Only established CLI contracts are tested; future paths are explicit additions.
- **Schema and invariant validation.** Never assert household-specific names, values, counts, or composition.
- **No mutation evidence here.** Split and other mutation live tests require a future disposable-fixture design.

## Acceptance Criteria

- [ ] The suite is skipped unless `MONARCH_LIVE_TESTS=1` (or its documented deliberate equivalent) is present and normal CI never sets that opt-in.
- [ ] The read-only opt-in cannot collect or run any mutation test; existing live mutation tests are removed or placed behind a separate stronger gate and marker.
- [ ] The documented initial matrix exercises auth ping/status, accounts list, a small transaction page, categories list, budgets list, and cashflow summary through the installed CLI.
- [ ] Holdings/reporting paths are absent until their public CLI contracts exist, then require an explicit reviewed matrix addition rather than an implicit “when supported” branch.
- [ ] Every selected command is classified read-only by shared operation metadata; refresh, login replacement, upload, transaction/account edit, and destructive operations are rejected by suite-level assertions.
- [ ] Assertions validate response shape, published schema conformance, normalization, and stable invariants without assuming balances, names, record counts, or household composition.
- [ ] Each command has a documented record/page limit and timeout; the suite has a documented maximum request count and inter-request delay/throttling policy.
- [ ] Missing authentication is a clear prerequisite failure; unsupported optional capabilities use explicit skip semantics and genuine contract drift fails.
- [ ] Failures identify the command/schema/invariant without printing tokens, cookies, raw response bodies, local credential paths, or unnecessary financial records.
- [ ] Local execution and release-check documentation state prerequisites, safety properties, exact matrix, maximum requests, expected runtime, and interpretation of skips/failures.
- [ ] Tests prove the read-only gate remains opt-in, excluded from CI, and unable to select separately gated mutation tests.
- [ ] `mc-3437` infrastructure/documentation is completed rather than duplicated, and repository verification passes.
