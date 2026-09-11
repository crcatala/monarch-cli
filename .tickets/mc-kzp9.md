---
id: mc-kzp9
status: open
deps: []
links: [mc-7wqj, mc-h3cl]
created: 2026-09-11T12:20:08Z
type: task
priority: 3
assignee: cc-vps
parent: mc-cr09
tags: [p3, credit, privacy, read-only, research]
---
# Evaluate read-only credit history exposure

Determine whether credit-history data has sufficient user value, availability, privacy boundaries, and stable semantics to justify a public CLI contract. This ticket is research and decision only. A go decision creates a separately scoped implementation ticket; it does not add a public command here.

## Design

The released upstream `get_credit_history()` response combines credit-score snapshots with household member identity, profile metadata, and Spinwheel onboarding/tracking state. Study the payload using synthetic fixtures, sanitized structural evidence, and—only when needed—a dedicated opt-in live probe. Do not use this research endpoint as the household-member transport for mc-iarh.

A live probe requires `MONARCH_CREDIT_HISTORY_RESEARCH=1`, is excluded from normal CI and both ordinary live suites, performs no remote mutation, and emits only a field/type/state summary suitable for review. It must never print or persist the raw response, score values, names/display names, profile-picture URLs, third-party IDs, onboarding error text, credentials, or unrelated household data. Any local ephemeral inspection material remains outside the repository and is deleted after producing the sanitized summary.

Study enrolled, unavailable/unenrolled, partially onboarded/error, unsupported-region, and multi-member behavior where observable. When a state cannot be observed safely, record it explicitly as unknown rather than manufacturing a fixture claim. Verify whether `creditScoreSnapshots[].user.id` maps to the same stable household member IDs exposed by the dedicated household directory and whether each household member has independent enrollment/history. Product documentation is supporting evidence, not a substitute for observed API semantics.

Record the result in `docs/research/credit-history-decision.md`. The decision document includes sanitized payload shapes, evidence provenance and confidence, upstream compatibility floor, user value, intended command hierarchy if any, regional and enrollment availability, update cadence, household ownership semantics, privacy-minimized candidate fields, unavailable/error state model, raw-mode policy, automation stability, remaining unknowns, and a clear go/no-go rationale.

Current official product documentation says the feature is supplied through Spinwheel/Equifax, is US-only, updates credit scores monthly, and requires each household member to connect independently. Validate how those product facts appear—or fail to appear—in the API response. Do not infer financial advice, score meaning, bureau completeness, refresh guarantees, or enrollment status beyond evidence.

A go decision must propose only the minimum normalized fields needed for score history and status: candidate score, reported date, stable member ID when verified, and an explicit availability/enrollment status. It must exclude names, display names, profile-picture URLs, `me.id`, duplicated nested user IDs, Spinwheel user/subscription identifiers, onboarding error details, bill-sync state, and other household/profile metadata unless a later review individually justifies them. Raw mode should default to prohibited because the upstream payload crosses these privacy boundaries.

A no-go decision may close this ticket without a public command. A go decision creates a focused child ticket that depends on mc-h3cl and owns implementation, output schemas/formats, dependency floor, tests, privacy regression coverage, and documentation.

## Key Decisions

- **Research and implementation are separate.** Payload uncertainty is resolved before defining a public command PR.
- **Dedicated sensitive-data opt-in.** Credit research is not silently included in general read-only live smoke coverage.
- **No raw payload retention.** Evidence records structure and states, not personal values or identifiers.
- **Unknown is an acceptable research result.** Unobservable household/enrollment cases are documented rather than guessed.
- **Raw public output is presumed prohibited.** A later proposal must explicitly overturn that privacy default with rationale.
- **Normalization dependency follows a go decision.** mc-h3cl does not block this research ticket; it blocks the implementation child if one is created.

## Decision Gate

Before closing this ticket, record a go/no-go decision covering:

- observed and unobserved payload shapes, provenance, confidence, and upstream compatibility floor;
- user value, regional/product availability, cadence, and intended command hierarchy;
- household ownership, per-member enrollment, and multi-member semantics;
- privacy-minimized candidate fields and explicit exclusions;
- unavailable, unenrolled, partial, unsupported-region, and error state model;
- raw-mode policy and sensitive-data handling;
- whether the contract is stable enough for automation;
- remaining unknowns and why they are acceptable or blocking.

## Acceptance Criteria

- [ ] `docs/research/credit-history-decision.md` records sanitized structural evidence, provenance/confidence, remaining unknowns, and a clear go/no-go decision using every Decision Gate category.
- [ ] Evidence covers enrolled, unavailable/unenrolled, partial/error, unsupported-region, and multi-member behavior where safely observable; unobservable states are explicitly recorded as unknown with the attempted evidence source.
- [ ] Product claims about US-only availability, monthly score updates, Spinwheel/Equifax sourcing, and independent household-member connection are compared with observed API behavior and are not treated as API guarantees without evidence.
- [ ] Any live probe requires `MONARCH_CREDIT_HISTORY_RESEARCH=1`, is excluded from CI and both ordinary live-test gates, performs no mutation, and cannot emit or persist a raw response.
- [ ] Tests or structural assertions prove probe/research output excludes score values, names/display names, profile URLs, `me.id`, nested user IDs, Spinwheel user/subscription IDs, onboarding error text, credentials, and unrelated household/profile data.
- [ ] Temporary sensitive inspection material is kept outside the repository, is not included in logs or failure output, and is deleted after the sanitized summary is produced.
- [ ] The decision verifies or explicitly leaves unknown the relationship between snapshot user IDs, household-member IDs, and independent per-member enrollment/history.
- [ ] If no-go, the document explains whether the feature is rejected or deferred, identifies what evidence could reopen the decision, and introduces no public command or normalized contract.
- [ ] If go, the document proposes minimum score/date/member/status fields, an explicit availability model, a default prohibition on raw output, command placement, and the exact upstream compatibility evidence.
- [ ] A go decision creates a separately scoped implementation child depending on mc-h3cl; this ticket itself adds no public command, transformer contract, or production endpoint.
- [ ] The research remains read-only, never enrolls users, triggers refreshes, changes tracking, or provides financial advice or derived credit claims.
- [ ] Repository verification passes for any checked-in probe, synthetic fixture, test, or decision-document changes.
