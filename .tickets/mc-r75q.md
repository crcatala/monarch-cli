---
id: mc-r75q
status: open
deps: [mc-4edf]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, accounts, liabilities, debt, read-only, normalization]
---
# Expose liability and debt-service account metadata

Provide the account metadata needed to understand liabilities and debt obligations from the CLI. A balance alone is insufficient for credit and loan accounts: users may need to distinguish liabilities from assets and inspect credit limits, rates, minimum payments, planned payments, and debt-paydown participation for analysis and planning.

The goal is a stable read-only representation that enables debt summaries and automation without forcing callers to depend on raw upstream payload names or infer financially meaningful values from missing data.

## Design

Inventory the liability fields reliably returned for each relevant account type and decide whether they belong in the common account schema, a detailed account view, or a dedicated liability view. Prefer optional values over fabricated zeros. Preserve units and semantics for rates, limits, and payments, and document whether values are current snapshots or settings.

Keep normalization in the account domain boundary and avoid making the default table excessively wide. Raw output remains opt-in and unmodified. This ticket should establish data access and semantics, not calculate payoff schedules or financial advice.

## Acceptance Criteria

- [ ] Users can reliably distinguish liability accounts from assets in normalized output.
- [ ] Supported liability metadata includes documented stable fields for credit limit, APR/interest rate, minimum payment, planned payment, and debt-paydown exclusion or equivalent available concepts.
- [ ] The design explicitly decides which fields appear in account list output versus a detail/liability-specific view.
- [ ] Missing, null, zero, negative, and inapplicable values remain distinguishable and do not produce invented financial values.
- [ ] Rate and currency-like fields have documented units, precision, and display behavior.
- [ ] Manual, hidden, deactivated, credit, loan, and ordinary asset accounts normalize without crashes or misleading liability fields.
- [ ] JSON and human-readable output are useful and stable; raw output remains unmodified.
- [ ] No payoff projections, recommendations, or unsupported derived financial claims are introduced.
- [ ] Unit and CLI tests cover representative liability types, non-liability accounts, partial payloads, and output formats.
- [ ] The required upstream-client compatibility floor is declared and covered by clean-install/contract verification.
- [ ] Output-contract and user documentation are updated and repository verification passes.
