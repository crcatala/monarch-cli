---
id: mc-t9o7
status: open
deps: [mc-k48z]
links: []
created: 2026-09-11T01:15:13Z
type: task
priority: 0
assignee: cc-vps
parent: mc-cr09
tags: [p0, safety, mutations, retries, idempotency]
---
# Make mutation execution retry-safe and partial-failure aware

Prevent duplicate or misleading financial changes when a network failure occurs around a mutation. The generic API executor currently retries transient failures, but a timed-out update, refresh, upload, or create may already have succeeded remotely. Retrying can repeat an undocumented side effect. Multi-step workflows can also partially succeed and need a consistent way to report and recover from that state.

This ticket extends the operation descriptor from `mc-k48z` with safe retry semantics and establishes one mutation outcome contract for current and future remote mutations.

## Design

Inventory the current remote mutation call sites: account refresh, transaction update, and transaction batch update. Record remote login/session establishment as reviewed but outside the financial mutation executor, and record local credential writes/deletes as out of scope.

Separate read and mutation execution APIs. Reads retain bounded retry behavior from configuration. All current remote mutations default to zero automatic retries after timeout, disconnect, or other ambiguous transport failure. Even an absolute-value update must not be assumed retry-safe based only on final-state intuition because the upstream service may have undocumented audit, timestamp, notification, or job-trigger effects.

A future mutation retry requires a named operation-specific mechanism such as an upstream idempotency key or tested read-after-write verification. Do not expose a generic `safe_to_retry=True` switch. Shared APIs should make the conservative path the default and require explicit policy evidence to select anything else.

Once remote execution is attempted, return a shared mutation outcome envelope. Pre-execution authorization and input-validation failures continue to use the structured error contract. Mutation outcomes use these top-level statuses:

- `succeeded`: every requested effect is known to have succeeded.
- `failed`: no requested effect succeeded and failures are known to be definitive.
- `ambiguous`: no effect is known to have succeeded, but at least one request may have changed remote state.
- `partial`: a multi-step operation contains a mixture of succeeded, failed, or ambiguous item outcomes.

Per-item statuses are `succeeded`, `failed`, or `ambiguous`. Preserve input order and include stable operation, entity, identifier, status, result/error metadata, summary counts, and a safe verification instruction where needed. Errors must be structured and sanitized rather than copied from arbitrary exception strings. Do not claim rollback or transactionality that the upstream API does not provide.

Treat timeout, disconnect, cancellation after request invocation, and similar transport failures as ambiguous unless there is affirmative evidence that no request could have reached the service. A definite GraphQL/application rejection may be reported as failed.

Exit behavior is part of the contract: all-succeeded outcomes exit `0`; definitive failed outcomes use the normal operation/API nonzero exit; partial or ambiguous outcomes exit `4`. Stdout contains the requested mutation outcome format; diagnostics and incidental progress remain off stdout.

## Key Decisions

- **No automatic retry for any current mutation.** Safety does not depend on undocumented upstream idempotency.
- **Ambiguous is not failed.** Once a request may have been dispatched, the CLI must not claim that nothing changed.
- **One envelope for single and batch operations.** Domain tickets consume the same contract rather than inventing command-specific shapes.
- **Nonzero partial outcomes.** A batch with any failed or ambiguous item is not successful automation, even if other items succeeded.
- **Explicit safety mechanisms, not booleans.** Any future retry policy names and tests the mechanism that makes it safe.

## Acceptance Criteria

- [ ] Account refresh, transaction update, and transaction batch update have documented retry/idempotency classifications in the shared operation model.
- [ ] Remote login/session establishment and local credential changes are explicitly inventoried as outside the financial mutation executor so the scope is not ambiguous.
- [ ] Reads retain appropriate configured bounded retries.
- [ ] All current remote mutations make only one attempt after timeout, disconnect, cancellation-after-invocation, or another ambiguous transport failure.
- [ ] Any future retry-enabled mutation must select a named idempotency-key or verified read-after-write policy with operation-specific tests; no generic unsafe boolean override exists.
- [ ] Shared execution APIs default mutations to no retry and make it difficult to route a remote mutation through the read retry policy.
- [ ] Once remote execution is attempted, single and multi-step mutations return the shared outcome envelope with stable operation, entity, identifier, status, result/error, summary, and verification metadata as applicable.
- [ ] Top-level status aggregation is deterministic: all succeeded → `succeeded`; no success and only definitive failures → `failed`; no success with any ambiguous item → `ambiguous`; mixed item outcomes → `partial`.
- [ ] Batch results preserve input order and include identifiers for succeeded, failed, and ambiguous items, not only failures.
- [ ] Transport uncertainty is reported as `ambiguous`, states that remote state may have changed, and provides a domain-appropriate safe verification step.
- [ ] Structured errors are sanitized and do not expose credentials, raw request bodies, or arbitrary upstream exception text.
- [ ] All-succeeded outcomes exit `0`; definitive failures use the documented normal nonzero error exit; partial and ambiguous outcomes exit `4`.
- [ ] Unit tests simulate timeout and disconnect before a response and prove that duplicate mutation attempts are not made.
- [ ] Tests cover definite upstream rejection separately from ambiguous transport failure.
- [ ] Regression tests cover account refresh, single transaction update, and batch update success, failure, ambiguous, mixed, and cancellation paths.
- [ ] Documentation defines read and mutation retry behavior, per-attempt timeout semantics, outcome aggregation, exit codes, and safe recovery for human and automated callers.
- [ ] Repository verification passes.

## Notes

**2026-09-11T01:21:50Z**

P1 planning clarification: this ticket should establish the shared mutation outcome envelope for both single-step and multi-step writes (including stable entity/id/status/result/error metadata and explicit ambiguous or partial outcomes). Domain feature tickets should consume that contract rather than invent command-specific mutation response shapes.
