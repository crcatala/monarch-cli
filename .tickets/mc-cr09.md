---
id: mc-cr09
status: open
deps: []
links: [mc-3437]
created: 2026-09-11T01:15:13Z
type: epic
priority: 0
assignee: cc-vps
tags: [roadmap, safety, architecture, automation]
---
# Safe CLI Expansion and Automation

Expand Monarch CLI into a broader automation surface without weakening its safety, security, or maintainability. The CLI can modify sensitive financial state and is intended for both humans and agents, so new capabilities need explicit trust boundaries, predictable execution semantics, secure credential handling, stable machine-readable behavior, and a maintainable architecture.

This epic is the umbrella for the full P0-P3 roadmap. Child-ticket priority communicates sequencing: P0 establishes prerequisites; later children can cover read-only API expansion, additional authenticated workflows and data semantics, and developer/agent experience improvements. Keeping the work under one epic provides a coherent roadmap without forcing all changes into one release or PR.

## Design

Organize work as small, independently reviewable tickets and PRs. Cross-cutting safety primitives should land before commands that depend on them. Feature tickets should use shared policy and service boundaries rather than reimplementing guards in individual commands.

Expected roadmap lanes:
- P0: mutation authorization, safe mutation execution, secure session compatibility, and dependency/install reproducibility.
- P1: focused read-only and mutation command expansion built on the P0 foundation.
- P2: authentication modes and richer account/transaction semantics.
- P3: configuration UX, schemas, capability discovery, documentation, and other automation ergonomics.

Before creating later children, review existing open tickets and link or update them instead of duplicating equivalent work.

## Acceptance Criteria

- [ ] All P0 foundation tickets are complete before broad mutation or raw API expansion is released.
- [ ] Every child is scoped so it can be implemented and reviewed in a focused PR.
- [ ] New state-changing commands use the shared mutation authorization and execution policies.
- [ ] Security-sensitive changes include negative-path and regression tests.
- [ ] Machine-readable behavior and user-facing safety requirements are documented.
- [ ] Existing tickets are reused or linked where their scope overlaps this roadmap.
- [ ] The repository verification suite and clean-install smoke tests pass at each release boundary.

