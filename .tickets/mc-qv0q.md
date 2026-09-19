---
id: mc-qv0q
status: open
deps: []
links: []
created: 2026-09-19T01:19:38Z
type: epic
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [roadmap, cli, ux, breaking-change, safety, automation]
---
# Major-release CLI UX consistency and safety hardening

Coordinate the breaking CLI improvements planned for the next major release so commands have predictable invocation patterns for both humans and automation. The current command surface has good safety foundations, but several commands still mix positional mutation targets, root-only and leaf-local flags behave inconsistently, some mutations lack previews, and a few validation/error/help paths do not clearly communicate their contracts.

This epic intentionally allows breaking changes: there has been no formal release for the current surface and existing positional forms do not need compatibility shims. The goal is a coherent CLI style rather than preserving every historical invocation.

## Design

## Style decisions

- Keep positional identifiers for simple read-only single-resource commands where there is no ambiguity.
- Use explicit target options for mutations, especially when a command accepts more than one resource/value concept.
- Use repeatable options for multiple values instead of comma-delimited strings.
- Use separate typed options when a value may be an opaque ID or a human name.
- Keep global options before the command path; reconcile all examples with that grammar.
- Make structured/machine-readable output contracts deterministic regardless of TTY state.
- Preserve the existing mutation authorization, confirmation, ambiguity, verification, and no-automatic-retry policies.

Existing related work should be incorporated rather than duplicated: `mc-46gq` covers the tag assignment redesign and `mc-4z49` covers help/example auditing.

## Acceptance Criteria

- [ ] The next-major CLI invocation grammar and breaking-change policy are documented.
- [ ] Child work establishes a consistent mutation-target, multi-value, output, preview, and validation style across affected commands.
- [ ] Existing tag redesign work is tracked under this epic and does not retain positional compatibility.
- [ ] Existing help/documentation polish is reconciled with the new syntax and global-option grammar.
- [ ] Safety behavior remains explicit: remote writes require `--allow-mutations`, confirmations remain separate from authorization, and ambiguous writes are never silently retried.
- [ ] Machine-readable output and exit-code behavior remain stable or are deliberately versioned/documented for the major release.
- [ ] Unit/CLI tests and repository verification cover the new invocation contracts and representative failure paths.

