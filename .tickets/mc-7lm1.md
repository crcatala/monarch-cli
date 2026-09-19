---
id: mc-7lm1
status: open
deps: []
links: []
created: 2026-09-19T01:19:38Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-qv0q
tags: [transactions, tags, splits, mutations, safety, ux]
---
# Add dry-run previews for complete-set tag and split mutations

Transaction updates already offer `--dry-run`, but complete-set tag and split mutations do not. Those operations are especially suitable for previews because they resolve current state and calculate the exact final set before writing. Adding previews gives humans and agents a safe way to inspect the effect before authorizing a remote write.

## Design

Add `--dry-run` to tag `replace`/`set`, tag `add`, tag `clear`, split `replace`, and split `clear`. A dry run may authenticate and perform read-only discovery/validation, including reading a split parent amount, but must never call a mutation endpoint, require `--allow-mutations`, or prompt for destructive confirmation.

Use a clear preview result rather than `mutation-outcome.v1`, because no remote write was attempted. Include the resolved target, current state when read, requested/final state, and the operation-specific facts needed to explain what would happen. For additive operations, report added/already-present IDs; for split replacement, report the validated parent total and requested rows.

## Acceptance Criteria

- [ ] `transactions tags replace` and its `set` alias accept `--dry-run`.
- [ ] `transactions tags add` and `transactions tags clear` accept `--dry-run`.
- [ ] `transactions splits replace` and `transactions splits clear` accept `--dry-run`.
- [ ] Dry-run executions perform only authentication/read/discovery/validation work and never invoke the corresponding mutation endpoint.
- [ ] Dry-run executions do not require `--allow-mutations`, do not require `--yes`, and do not prompt for confirmation.
- [ ] Tag previews show resolved tag IDs/names, current assignment, requested/final assignment, and no-op/additive details where relevant.
- [ ] Split previews validate the parent amount and input constraints and show the intended split set without claiming remote application.
- [ ] Dry-run output has a documented stable status and remains distinct from `mutation-outcome.v1` because no remote effect was attempted.
- [ ] Tests prove no mutation call occurs, including non-interactive and malformed-input paths.
- [ ] Help and documentation include safe preview examples and repository verification passes.

