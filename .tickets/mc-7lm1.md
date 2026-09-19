---
id: mc-7lm1
status: closed
deps: [mc-46gq, mc-s6s6]
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

Add `--dry-run` to tag `replace`, tag `add`, tag `clear`, split `replace`, and split `clear`. A dry run may authenticate and perform read-only discovery/validation, including reading a split parent amount, but must never call a mutation endpoint, require `--allow-mutations`, or prompt for destructive confirmation. `--dry-run --yes` is accepted and documented as irrelevant: a preview has no confirmation step to skip.

Preview results follow one rule for every command:

- `status` is always `"dry_run"`, so a preview can never be confused with an applied write or with `mutation-outcome.v1`.
- Include the operation and the resolved target, plus a command-specific detail object explaining what would happen: for tags, resolved IDs/names, current assignment, requested/final assignment, added/already-present IDs, and no-op state; for splits, the validated parent total and the intended rows.
- The detail object is informational. It is not a second stable schema family, and `mc-cpzi` may decide later whether previews are schematized.
- Previews use the same JSON emission path as mutation outcomes and are never re-rendered or swallowed by `--quiet`/`--format` (`mc-hu2c`).

Reuse the shared mutation primitives extracted by `mc-46gq` where applicable; do not add command-local preview frameworks.

## Acceptance Criteria

- [ ] `transactions tags replace`, `transactions tags add`, and `transactions tags clear` accept `--dry-run`.
- [ ] `transactions splits replace` and `transactions splits clear` accept `--dry-run`.
- [ ] Dry-run executions perform only authentication/read/discovery/validation work and never invoke the corresponding mutation endpoint.
- [ ] Dry-run executions do not require `--allow-mutations`, do not require `--yes`, and do not prompt for confirmation.
- [ ] `--dry-run --yes` is accepted and documented as a no-op rather than rejected.
- [ ] Tag previews show resolved tag IDs/names, current assignment, requested/final assignment, and no-op/additive details where relevant.
- [ ] Split previews validate the parent amount and input constraints and show the intended split set without claiming remote application.
- [ ] Every dry-run result carries the documented `status: "dry_run"` discriminator plus the operation and target, and remains distinct from `mutation-outcome.v1`; it is not registered as a new stable schema family.
- [ ] Previews are never rendered through or silenced by `--quiet`/`--format`; they use the shared JSON emission path.
- [ ] Tests prove no mutation call occurs, including non-interactive and malformed-input paths, and cover the preview discriminator.
- [ ] Help and documentation include safe preview examples and repository verification passes.

## Notes

**2026-09-19T13:14:53Z**

Supplemental human verification (2026-09-19): tag and split dry-run previews returned the dry_run discriminator without changing remote state. A split set applied afterward matched the preview, and the split assignment was cleared back to its original empty state. No credentials or record identifiers are recorded.
