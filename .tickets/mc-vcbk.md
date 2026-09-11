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

Detect drift between mocked assumptions and the authenticated service before releases. Unit tests can verify our code while still missing renamed fields, changed nullability, unsupported filters, or altered response envelopes. A deliberately small, opt-in live smoke suite provides evidence that critical read-only contracts still work without placing credentials or financial data in CI.

## Design

Build on the local-only live-test infrastructure rather than creating a second runner. Select a bounded matrix of representative read-only service and CLI calls, validate shapes and invariants rather than a particular household's values, and reuse published schema/normalization contracts where practical. The suite must be disabled by default, avoid remote writes, minimize requests, redact diagnostics, and produce a concise release-check result. Mutation contract testing requires a separate disposable-fixture design and is out of scope.

## Acceptance Criteria

- [ ] The suite is skipped unless a deliberate live-test opt-in is present and is never enabled by normal CI configuration.
- [ ] It exercises a documented bounded set of critical read-only API and CLI paths across accounts, transactions, categories, reporting, and holdings when supported.
- [ ] Assertions validate response shape, normalization, and stable invariants without assuming specific balances, names, record counts, or household composition.
- [ ] The suite performs no remote mutation, refresh, upload, login replacement, or destructive operation.
- [ ] Request count, pagination, timeout, and throttling behavior are bounded to avoid rate-limit or abuse risk.
- [ ] Failures identify the affected contract without printing tokens, cookies, or unnecessary financial records.
- [ ] Missing authentication and unsupported optional capabilities produce clear skip/failure semantics.
- [ ] Local execution and release-check documentation state prerequisites, safety properties, and expected runtime.
- [ ] Tests verify the suite remains opt-in and excluded from CI.
- [ ] Repository verification passes.

