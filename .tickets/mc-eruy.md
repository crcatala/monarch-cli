---
id: mc-eruy
status: open
deps: [mc-h3cl]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, transactions, rules, read-only, automation]
---
# Add read-only transaction rule inspection

Expose configured transaction rules so users can explain automatic categorization and other recurring behavior without opening the web interface. Read-only rule inspection also lets automation diagnose why a transaction changed and assess existing policy before proposing new mutations.

## Design

Create a read-only rules service and command surface that preserves rule identity and priority while normalizing criteria and actions into an extensible contract. Rules are heterogeneous and may gain new criterion/action types, so unknown variants must remain inspectable without being misrepresented or crashing. Editing, creating, deleting, or simulating rules is out of scope.

## Acceptance Criteria

- [ ] Users can list transaction rules in their effective deterministic priority order.
- [ ] Normalized output preserves rule IDs, names/status when available, criteria, actions, and enough type information to interpret heterogeneous variants.
- [ ] Unknown or newly introduced criterion/action variants remain visible as explicitly unsupported data rather than being dropped or mislabeled.
- [ ] Empty, disabled, partial, null, and malformed rule data have documented non-misleading behavior.
- [ ] JSON output supports automation and human-readable output remains legible for nested rule structures.
- [ ] The feature performs no remote mutation and does not claim to simulate final service behavior.
- [ ] Adapter/service/transformer boundaries isolate dependency-specific response shapes.
- [ ] Tests cover ordering, representative criterion/action variants, unknown variants, empty/partial responses, formats, and errors.
- [ ] The feature is enabled only against a declared stable compatible dependency surface.
- [ ] User-facing documentation and repository verification are complete.

