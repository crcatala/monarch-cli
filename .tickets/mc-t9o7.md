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
# Make remote mutation execution retry-safe and ambiguity-aware

Prevent duplicate or misleading financial changes when a network failure occurs around a mutation. The generic API executor currently retries transient failures, but a timed-out update or refresh may already have succeeded remotely. Retrying can repeat an undocumented side effect, while reporting the request as an ordinary failure can falsely imply that remote state did not change.

This ticket extends the operation descriptor from `mc-k48z` with conservative execution semantics. The reusable single/batch outcome envelope is intentionally separated into `mc-ik8o`.

## Design

Inventory the current remote mutation call sites: account refresh, transaction update, and each item in transaction batch update. Authentication is explicitly a composite `remote_authentication` plus `local_credential_change` operation under the `mc-k48z` taxonomy, but it remains outside this financial mutation executor. Local credential writes/deletes are likewise outside this ticket's execution scope. This is an intentional policy boundary, not a claim that login is purely local.

Separate read and mutation execution APIs. Reads retain bounded retry behavior from configuration. All current remote mutations default to zero automatic retries after timeout, disconnect, cancellation after request invocation, or another ambiguous transport failure. Even an absolute-value update must not be assumed retry-safe based only on final-state intuition because the upstream service may have undocumented audit, timestamp, notification, or job-trigger effects.

A future mutation retry requires a named operation-specific mechanism such as an upstream idempotency key or tested read-after-write verification. Do not expose a generic `safe_to_retry=True` switch. Shared APIs should make the conservative path the default and require explicit policy evidence to select anything else.

Once a mutation request may have been dispatched, transport uncertainty is `MUTATION_AMBIGUOUS`, not an ordinary network failure. The structured error must identify the stable operation and affected entity identifier(s), state that remote state may have changed, and provide a safe verification instruction. It exits with code `4`. A definite GraphQL/application rejection remains a normal failed operation and uses the existing API error path.

Batch update does not need to adopt the shared v1 envelope in this ticket, but it must retain every per-item outcome, distinguish ambiguous items from definite failures, preserve input order, and exit nonzero when any item is failed or ambiguous. `mc-ik8o` will normalize that command-specific interim result into the shared contract before downstream mutation features ship.

## Key Decisions

- **No automatic retry for any current mutation.** Safety does not depend on undocumented upstream idempotency.
- **Ambiguous is not failed.** Once a request may have been dispatched, the CLI must not claim that nothing changed.
- **Explicit safety mechanisms, not booleans.** Any future retry policy names and tests the mechanism that makes it safe.
- **Keep this PR focused on execution.** Shared output aggregation, schema versioning, and reusable envelope semantics belong to `mc-ik8o`.

## Acceptance Criteria

- [ ] Account refresh, transaction update, and each transaction batch-update item have documented retry/idempotency classifications in the shared operation model.
- [ ] Authentication is recorded as a composite `remote_authentication` plus `local_credential_change` operation that is intentionally outside the financial mutation executor.
- [ ] Reads retain appropriate configured bounded retries.
- [ ] All current remote mutations make only one attempt after timeout, disconnect, cancellation-after-invocation, or another ambiguous transport failure.
- [ ] Any future retry-enabled mutation must select a named idempotency-key or verified read-after-write policy with operation-specific tests; no generic unsafe boolean override exists.
- [ ] Shared execution APIs default mutations to no retry and make it difficult to route a remote mutation through the read retry policy.
- [ ] Transport uncertainty raises or returns `MUTATION_AMBIGUOUS`, exits with code `4`, states that remote state may have changed, and provides a domain-appropriate safe verification step.
- [ ] Ambiguous structured errors identify the stable operation and affected entity identifier(s) without exposing credentials, raw request bodies, or arbitrary upstream exception text.
- [ ] Definite GraphQL/application rejection is distinguishable from ambiguous transport failure and uses the normal API error path.
- [ ] Batch update preserves ordered per-item results, labels transport uncertainty as ambiguous rather than failed, and exits nonzero when any item is failed or ambiguous.
- [ ] Unit tests simulate timeout and disconnect before a response and prove duplicate mutation attempts are not made.
- [ ] Regression tests cover account refresh, single transaction update, and batch-update success, definite failure, ambiguity, and cancellation paths.
- [ ] Documentation defines read and mutation retry behavior, per-attempt timeout semantics, ambiguity, exit code `4`, and safe verification guidance.
- [ ] Repository verification passes.

## Notes

**2026-09-11T01:21:50Z**

P1 planning originally placed the shared mutation outcome envelope in this ticket. That contract has been split into `mc-ik8o` so retry safety and output-contract adoption can each be implemented and reviewed in a focused PR.
