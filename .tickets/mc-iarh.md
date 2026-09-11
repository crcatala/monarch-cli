---
id: mc-iarh
status: open
deps: [mc-8dfd]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, household, ownership, read-only, discovery]
---
# Add read-only household member discovery

Let shared households resolve ownership identifiers to people before filtering, interpreting, or changing owned records. Ownership fields alone are difficult to use safely when the CLI cannot list the valid household members and distinguish member-owned, shared, and unassigned states.

## Design

Provide a small read-only household-domain command and service that returns a stable member directory with identifiers, display values, and roles when available. Define privacy-conscious human output and explicit semantics for shared/unassigned ownership. Keep member discovery separate from ownership mutation so it can land and be reviewed independently.

## Acceptance Criteria

- [ ] Users can list current household members through a discoverable read-only command.
- [ ] Normalized output includes stable member identifiers, useful display values, and role metadata when available.
- [ ] Empty households, single-member households, pending or unavailable members, null fields, and partial responses have documented semantics.
- [ ] Output does not expose unnecessary authentication or invitation metadata.
- [ ] JSON and human-readable formats are deterministic and useful for resolving owner IDs.
- [ ] The command performs no remote mutation and uses adapter/service/transformer boundaries.
- [ ] Tests cover complete, empty, null, partial, and malformed responses plus output formats and errors.
- [ ] The feature is enabled only against a declared stable compatible dependency surface.
- [ ] User-facing documentation and repository verification are complete.

