---
id: mc-hp7w
status: open
deps: [mc-k48z, mc-t9o7, mc-hszv]
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

Treat splits as a transaction subresource with inspection available without mutation authorization. Define whether updates replace the complete split set, how clearing works, and which fields belong in the CLI payload contract. Accept one documented schema from inline JSON or a readable file. Validate payload structure and totals locally where reliable while keeping the server authoritative. Use the shared mutation outcome envelope and never imply transactional behavior that the remote API does not provide.

## Acceptance Criteria

- [ ] Users can inspect the current splits for a transaction without mutation authorization.
- [ ] Authorized users can replace or clear splits using one documented payload schema accepted from inline JSON or a readable file.
- [ ] Replace-versus-merge and clear semantics are explicit and tested.
- [ ] Payload validation rejects malformed records, unsupported fields, invalid identifiers, non-finite or invalid amounts, duplicate entries where prohibited, and detectable total mismatches before mutation.
- [ ] Amount precision, sign conventions, and total-comparison tolerances are documented and tested.
- [ ] Every write is blocked by default and uses the shared mutation authorization and retry-safe execution policies.
- [ ] Mutation responses use the shared stable outcome envelope and represent rejected, ambiguous, or partial outcomes honestly.
- [ ] Read-after-write verification is performed or clearly supported where it improves safety without masking failure.
- [ ] Unit/CLI tests cover inspection, input sources, validation, authorization, replacement, clearing, remote failures, and output modes.
- [ ] User-facing safety documentation and repository verification are complete.

