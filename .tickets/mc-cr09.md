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
- P0: mutation authorization, retry-safe execution, shared mutation outcomes, deterministic non-interactive behavior, removal of unsafe legacy session compatibility, and dependency/install reproducibility.
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


## Notes

**2026-09-17T23:42:05Z**

Human Verification Checkpoint A evidence recorded (2026-09-17): the operator reports all critical verification scenarios completed, including clean shipped-wheel validation and approved disposable-household mutation smoke checks. The read-only live API smoke suite also passed via `MONARCH_LIVE_TESTS=1 make test-live`. Additional medium-priority verification was partially completed; only confirmed scope is recorded on the linked tickets. No credentials or raw financial payloads are recorded here. P0 implementation state remains complete; no downstream ticket is being closed by this note.

**2026-09-18T23:29:04Z**

Verification checkpoint update (2026-09-18): authenticated read-only checks for account reporting, transactions/recurring, cashflow, holdings, institutions, and subscription completed successfully. The disposable live mutation contract test passed for its approved dev household, including fixture lifecycle, notes round-trip, bounded readback, and cleanup. No personal account mutations, credentials, identifiers, balances, or raw payloads are recorded here.
