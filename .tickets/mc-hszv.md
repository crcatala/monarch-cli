---
id: mc-hszv
status: open
deps: [mc-h3cl]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, transactions, read-only, filters, inspection]
---
# Expand read-only transaction discovery and inspection

Provide enough read-only transaction coverage to locate, filter, and inspect the exact records a human or automated workflow may later act on. The current basic list view is insufficient for review queues, attachment workflows, recurring or split analysis, and safe pre-mutation verification.

## Design

Design a cohesive transaction query surface that extends listing filters and adds single-transaction detail inspection without exposing raw upstream shapes as the default contract. Candidate filters include category IDs, tag IDs, attachment/note presence, report visibility, split/recurring/pending state, import or sync origin, review state, and visibility scope. Validate enums and mutually exclusive options locally. Include duplicate discovery only if it can be presented as a read-only diagnostic with well-defined matching semantics and bounded pagination.

## Acceptance Criteria

- [ ] Users can fetch full read-only details for one transaction by ID.
- [ ] Transaction listing supports the reviewed set of high-value filters with repeatable multi-ID options where appropriate.
- [ ] Pending versus posted and needs-review versus reviewed semantics are explicit and tested.
- [ ] Invalid filter values and incompatible combinations fail before an API request.
- [ ] Normalized output is stable across JSON and human-readable formats, while an explicitly requested raw mode preserves upstream data.
- [ ] Pagination and limits are bounded and documented.
- [ ] If duplicate discovery is included, its match key, date/account scope, and false-positive limitations are documented and tested.
- [ ] No command in this ticket changes remote state.
- [ ] Unit/CLI tests verify API argument mapping, null response handling, empty results, output formats, and errors.
- [ ] User-facing command documentation and repository verification are complete.

