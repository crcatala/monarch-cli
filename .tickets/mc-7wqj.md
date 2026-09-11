---
id: mc-7wqj
status: open
deps: [mc-h3cl]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, reporting, cashflow, recurring, institutions, read-only]
---
# Expand read-only reporting and service context

Expose the read-only financial context needed for analysis and diagnostics beyond the current cashflow summary. Users should be able to inspect detailed cashflow, transaction aggregates, recurring activity, connected institutions, subscription state, and other supported summary information through predictable CLI contracts.

## Design

Inventory the available read methods and organize commands according to user-facing domains rather than placing unrelated resources under a convenient existing group. Likely areas include cashflow detail, transaction summary, recurring transactions, institution status, subscription details, and credit history. A design pass should decide whether small top-level groups or existing domain groups produce the clearest long-term navigation. Reuse common date-range, pagination, normalization, and output behavior.

## Acceptance Criteria

- [ ] Detailed cashflow data is available for validated date ranges in addition to the existing summary.
- [ ] Supported transaction aggregate/summary and recurring-activity reads are exposed with clear semantics.
- [ ] Institution and subscription status are available through a discoverable command hierarchy.
- [ ] Credit-history or similar read-only summary data is included only if its shape and user value can be documented reliably.
- [ ] Command grouping is justified by the domain model and avoids turning an unrelated command group into a catch-all.
- [ ] Shared date, pagination, normalization, and output utilities are reused.
- [ ] Null, empty, partial, and unavailable responses produce stable non-misleading output.
- [ ] No command in this ticket changes remote state.
- [ ] Unit/CLI tests verify API mapping, date behavior, output contracts, and negative paths.
- [ ] User-facing documentation and repository verification are complete.

