---
id: mc-nbvi
status: open
deps: [mc-h3cl]
links: [mc-7wqj]
created: 2026-09-11T12:20:08Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, transactions, reporting, recurring, read-only]
---
# Add transaction summary and recurring activity reads

Expose transaction aggregates and recurring activity through explicit read-only commands with semantics matching the released upstream API.

## Design

Add `transactions summary` and `transactions recurring` under the existing transaction domain. The released `get_transactions_summary` method accepts no filters or date range, so its output is explicitly an all-time aggregate and the command must not imply that transaction-list filters apply. The released recurring method accepts both start and end dates or neither and defaults to the current month; expose the shared date presets and reject invalid or one-sided ranges locally.

Normalize recurring stream identity, merchant, account, category, expected date, expected/observed amount, approximation, past status, and linked transaction ID without inventing unavailable values. Transaction summary normalization documents count, average, extrema, first/last values, income, expense, and net-sum semantics using the upstream fields actually returned.

Do not add recurring mutations, transaction-list filtering, cashflow detail, institution data, or subscription data in this ticket.

## Key Decisions

- **Transaction summary is all-time.** The released client exposes no date or filter parameters for this method.
- **Recurring activity is date-scoped.** It uses shared inclusive date-range and preset behavior.
- **Both commands stay under transactions.** A one-command top-level recurring group is unnecessary until a broader recurring domain exists.

## Acceptance Criteria

- [ ] `transactions summary` returns a documented normalized all-time aggregate and exposes no unsupported date or transaction-filter options.
- [ ] Summary output distinguishes count, average, maximum values, income, expenses, net sum, first, and last according to verified upstream semantics.
- [ ] `transactions recurring` returns normalized recurring items for the upstream default period and for explicit shared presets/date ranges.
- [ ] Recurring rows preserve stable stream, merchant, account, category, expected date, transaction, approximation, and amount fields when available.
- [ ] One-sided recurring ranges, invalid dates, and `start > end` fail before client creation or an API request.
- [ ] Null, empty, partial, and unavailable summary or recurring responses follow the shared normalization rules without fabricated financial values.
- [ ] JSON and human-readable formats have stable documented shapes; explicit raw mode preserves the corresponding upstream response.
- [ ] Both commands are classified read-only and perform no remote mutation.
- [ ] Unit/CLI tests verify API mapping, all-time summary behavior, recurring defaults/presets/ranges, validation-before-call, null/empty payloads, formats, and errors.
- [ ] The required upstream-client compatibility floor is verified, user-facing documentation is complete, and repository verification passes.
