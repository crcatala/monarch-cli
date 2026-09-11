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

Prevent duplicate or misleading financial changes when a network failure occurs around a mutation. The generic API executor retries transient failures, but a timed-out create, upload, or other non-idempotent request may already have succeeded remotely. Retrying it can duplicate data. Multi-step workflows can also partially succeed and currently lack a consistent way to report or resume that state.

This ticket defines and enforces safe execution semantics for all current and future mutations.

## Design

Inventory mutation call sites and classify them as idempotent, conditionally idempotent, or non-idempotent. Separate read retry policy from mutation retry policy. Non-idempotent operations should not retry automatically unless a documented idempotency key or verified read-after-write strategy makes the retry safe.

Define a structured outcome for multi-step workflows that distinguishes success, failure before any change, and partial success. Preserve enough information for a caller to inspect state and safely recover. Do not claim transactional behavior when the remote API does not provide it.

## Acceptance Criteria

- [ ] Every existing mutation call site has a documented retry/idempotency classification.
- [ ] Non-idempotent mutations do not automatically retry after ambiguous transport failures.
- [ ] Reads retain appropriate bounded retry behavior.
- [ ] Any allowed mutation retry has a documented and tested safety mechanism.
- [ ] Shared execution APIs make unsafe retry behavior difficult to select accidentally.
- [ ] Multi-step mutation workflows return a stable structured result that identifies completed and failed steps.
- [ ] Error output tells callers when remote state may have changed and recommends a safe verification step.
- [ ] Unit tests simulate timeout/disconnect-before-response cases and prove duplicate mutation attempts are not made.
- [ ] Regression tests cover current single and batch mutation commands.
- [ ] Retry, timeout, and partial-success behavior is documented for human and automated callers.

