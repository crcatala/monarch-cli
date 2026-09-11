---
id: mc-bf8f
status: open
deps: [mc-iarh, mc-k48z, mc-ik8o]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, transactions, household, ownership, mutation, safety]
---
# Add guarded transaction ownership updates

Allow shared households to assign a transaction to a member or return it to shared ownership through an explicit, auditable CLI workflow. Without this capability, ownership can be inspected but not corrected in automation. Because an incorrect assignment changes reporting and household interpretation, the workflow must build on the common mutation safety and partial-failure policies.

## Design

Model ownership assignment as a first-class transaction mutation using member IDs obtained from read-only discovery. Use explicit options for assigning a member and selecting shared ownership; do not overload empty strings or ambiguous booleans in the user-facing interface. Define dry-run/readback behavior and normalized mutation results. Reuse the central mutation authorization and execution path, validate mutually exclusive inputs locally, and avoid retrying an uncertain write.

## Acceptance Criteria

- [ ] An authorized mutation can assign one transaction to a valid household member ID.
- [ ] An authorized mutation can explicitly set the transaction to shared ownership.
- [ ] Assign-member and shared-ownership inputs are unambiguous, mutually exclusive, and validated before the request.
- [ ] Omitting ownership options never clears or changes existing ownership.
- [ ] The command supports dry-run or equivalent preview semantics without making an API request.
- [ ] Execution uses the shared remote-mutation authorization, retry-safety, error, and result-envelope policies.
- [ ] Success is verified through returned data or bounded readback, and uncertain/partial outcomes are reported without unsafe automatic retry.
- [ ] Tests cover member assignment, shared ownership, no-op input, invalid combinations, blocked authorization, API errors, and machine-readable output.
- [ ] The feature is enabled only against a declared stable compatible dependency surface.
- [ ] User-facing safety documentation and repository verification are complete.

