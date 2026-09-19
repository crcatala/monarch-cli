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

**2026-09-19T13:14:53Z**

Human verification checkpoint (2026-09-19): the owner-authenticated test development account was confirmed to expose exactly two accounts. The household identity gate matched, and no household ID or account/transaction identifiers were recorded.

The corrected disposable-fixture live mutation suite passed (1 selected test, 88 deselected), covering the explicit --transaction-id mutation path, mutation outcome handling, bounded readback, and cleanup. Supplemental verification for the delivered CLI UX work also passed: real-TTY preview and mutation JSON emission, tag add-by-name/add-by-ID/replace/clear, tag and split dry-run no-write behavior, split preview-to-apply fidelity, and real-TTY help review. Test-account tags and splits were restored to their original state. No credentials or raw financial payloads are recorded here.

**2026-09-19T17:51:52Z**

Human/agent verification phase executed — 2026-09-19, on an owner-authenticated disposable test account (2 manual accounts).

Passed:
- Read-only live suite: `MONARCH_LIVE_TESTS=1 make test-live` -> 20 passed.
- Per-ticket human steps: live attachment upload (mc-2v9a), live credential-safety capture (mc-sr92), review round trip + no-op (mc-e49c), transaction create/delete lifecycle (mc-yqfi), budget write + extended scope invariants (mc-9u99), live output validated against published schemas (mc-cpzi), capabilities manifest mechanics/accuracy (mc-82kf).
- Gated live mutation suite: `MONARCH_LIVE_MUTATION_TESTS=1 make test-live-mutation` -> test_transaction_notes_round_trip passed, fixtures self-cleaned.
- Forced attachment-registration failure -> `partial`/exit 4 with orphaned media acknowledged, no retry.

Open follow-ups:
- mc-ic7w (high): transport failures on dispatched mutations are misreported as definitive failures instead of ambiguous (gql TransportConnectionFailed not in the ambiguous set). Re-verify after the fix.
- mc-61tf (low): normalized transaction detail omits review metadata.
- F2 observation: manual-account balance drift on create/delete (Monarch-side; no CLI restore path).

Remaining human-only items: final UI confirmation, published-PyPI schema install (needs a release), upload-adapter maintenance assumptions, schema publication decision, macOS/Windows manifest run, manifest usefulness sign-off.
