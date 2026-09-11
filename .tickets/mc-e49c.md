---
id: mc-e49c
status: open
deps: [mc-k48z, mc-ik8o, mc-hszv]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, transactions, review, mutations, safety]
---
# Add explicit transaction review-state mutations

Allow a user or automated workflow to deliberately mark a transaction reviewed or return it to the review queue. Review state is operationally important for transaction triage, but superficially similar API fields can have different mutation semantics. An ambiguous boolean option could report success without producing the intended state.

The CLI should expose intent-oriented actions with verified outcomes, building on the read-only review filters and the shared mutation safety contracts.

## Design

Confirm and model the distinct meanings of “reviewed” and “needs review” at the service boundary. Prefer explicit user-facing operations or mutually exclusive options over a single overloaded boolean pair. Map each intent to the correct upstream mutation field and support read-after-write verification when practical.

Treat this as a state-changing workflow: require centralized mutation authorization, use retry-safe execution, and represent ambiguous or failed verification honestly. Do not infer success only because the transport returned without raising.

## Acceptance Criteria

- [ ] Users can explicitly mark one transaction reviewed.
- [ ] Users can explicitly return one transaction to the review queue.
- [ ] Command names/options make the two intents unambiguous and reject contradictory input before an API call.
- [ ] Each intent maps to the correct upstream mutation semantics and is covered by argument-mapping tests.
- [ ] Every review-state write is blocked by default and requires shared mutation authorization.
- [ ] Mutation execution does not automatically retry after an ambiguous non-idempotent failure.
- [ ] Successful output uses the shared mutation outcome contract and identifies the requested and observed state.
- [ ] Read-after-write verification is performed, or an explicit reason and safe verification command are provided when verification is unavailable.
- [ ] No-op, already-in-state, not-found, permission, server-rejection, timeout, ambiguous, and verification-mismatch paths are handled deterministically.
- [ ] Read-only pending/posted and review-queue filters remain semantically aligned with the mutation behavior.
- [ ] Unit/CLI tests cover authorization, both transitions, invalid combinations, output modes, and negative paths.
- [ ] User-facing workflow documentation is complete and repository verification passes.
