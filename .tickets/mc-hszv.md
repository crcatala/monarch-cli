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

Add `transactions get TRANSACTION_ID` and extend `transactions list` with the filters supported by the released upstream client: repeatable category, account, and tag IDs; attachment, note, report-hidden, split, recurring, pending, import-origin, institution-sync, and needs-review tri-state filters; and transaction visibility scope. Boolean filters must distinguish omitted, true, and false rather than accepting string booleans.

Pending/posted state and review state are orthogonal. Normalized list/detail output exposes them separately and maps pending from the upstream `pending` field. `get_transaction_details` may redirect a pending identifier to its posted replacement; retain the upstream default but expose a strict no-redirect option and always make requested-versus-returned identity observable.

Validate complete date pairs, date ordering, enum values, positive bounded limits, and nonnegative offsets before client creation or API calls. Keep the existing bare-list normalized output backward compatible. Raw mode exposes untouched upstream pagination metadata; a new normalized metadata envelope is outside this ticket.

Duplicate discovery is explicitly out of scope because it requires a separate match-key, scan-bound, and false-positive policy. Transaction aggregates and split/tag mutation workflows are also owned by separate tickets.

## Key Decisions

- **Ship the complete released filter surface.** The marginal implementation cost per filter is small, and documenting a partial arbitrary subset would make automation harder.
- **Tri-state booleans are explicit.** Omission means no filter; positive and negative flags map to `True` and `False`.
- **Identity redirects are visible.** Detail output never silently hides that a pending ID resolved to a posted transaction.
- **Normalized pagination remains backward compatible.** Default output remains a list; callers needing upstream `totalCount` use explicit raw mode until a separately designed metadata envelope exists.
- **No duplicate detector in this PR.** It is not a server capability and needs its own bounded diagnostic design.

## Acceptance Criteria

- [ ] `transactions get TRANSACTION_ID` returns normalized read-only detail and supports an explicit strict/no-posted-redirect mode.
- [ ] Detail output includes the requested ID, returned transaction ID, original transaction identity when available, pending state, review state, attachments, tags, and split summary without exposing raw upstream structure by default.
- [ ] `transactions list` supports repeatable category, account, and tag filters and tri-state filters for attachment presence, note presence, report visibility, split, recurring, pending, import origin, institution sync, and needs-review state, plus the supported visibility enum.
- [ ] Pending/posted, needs-review, and opaque upstream review status remain distinct normalized concepts and are tested in independent combinations.
- [ ] The pending transformer uses the real upstream `pending` key and tests use representative upstream fixtures.
- [ ] Omitted tri-state options are omitted from API filtering; positive and negative forms map deterministically to `True` and `False`.
- [ ] One-sided ranges, `start > end`, invalid enums, nonpositive or over-cap limits, and negative offsets fail before client creation or an API request.
- [ ] The maximum page size is documented; default normalized list output remains backward-compatible, and explicit raw mode preserves `totalCount` and the upstream envelope.
- [ ] Null detail objects, null/empty result containers, not-found responses, redirect behavior, and malformed upstream payloads produce stable output or typed errors.
- [ ] No command in this ticket changes remote state, discovers duplicates, mutates review state, or implements transaction aggregates.
- [ ] The minimum dependency is raised to `monarchmoneycommunity>=1.5.2`, the lockfile is consistent, and client-interface tests require the new methods and pending-filter signature.
- [ ] Unit/CLI tests verify every API argument mapping, validation-before-call behavior, output format, empty result, and negative path.
- [ ] User-facing command and pagination documentation is complete and repository verification passes.


## Notes

**2026-09-11T01:36:40Z**

P2 planning clarification: this ticket owns the read-only pending/posted filter and the distinction between pending state and review state. Ensure the implementation maps the supported upstream pending filter explicitly, updates the minimum compatible dependency metadata when needed, and tests both positive and negative forms. Do not create a separate pending-filter ticket.
