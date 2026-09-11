---
id: mc-4edf
status: open
deps: [mc-h3cl, mc-7xfl]
links: [mc-7xfl, mc-7wqj]
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, accounts, read-only, history, snapshots, sync]
---
# Expand read-only account history, snapshots, and refresh visibility

Enable users to understand account balance history, net-worth trends, and synchronization state without leaving the CLI. These read paths also provide the verification data needed before and after future account-management workflows.

## Design

Add account-domain read commands: `accounts history ACCOUNT_ID`, `accounts recent-balances`, `accounts snapshots`, `accounts snapshots-by-type`, and `accounts refresh-status`. Keep account type/subtype discovery in `mc-7xfl`; this ticket may consume that service only to validate snapshot filters.

Match each command to released upstream capabilities rather than pretending they share one range model: recent balances accept a start date only; type-scoped snapshots accept a start date and `month|year` timeframe; aggregate snapshots accept start and end dates. Reuse shared date parsing and validate ordering wherever two bounds exist.

Treat identifiers as opaque non-empty strings and never coerce them to integers despite an inaccurate upstream annotation. A directly identified hidden, manual, or deactivated account remains readable. Normalized empty histories are empty collections rather than invented values.

Refresh status is observational only. The released client returns an aggregate boolean and can incorrectly report completion when requested IDs are unknown. Validate requested IDs against account discovery before checking status; unknown IDs are reported as unknown and never folded into a successful completion result. Do not add polling, waiting, or refresh initiation. Existing `accounts refresh` remains a separate `remote_mutation` operation.

## Key Decisions

- **No duplicate type-discovery command.** `mc-7xfl` owns the normalized account-type hierarchy.
- **Date options reflect the API.** End dates are accepted only by aggregate snapshots.
- **Unknown refresh targets never mean complete.** The service masks the upstream empty-selection behavior.
- **All new commands are read-only.** This ticket does not modify the existing refresh mutation.

## Acceptance Criteria

- [ ] A user can retrieve normalized balance history for one opaque string account ID; no numeric coercion is performed.
- [ ] A user can retrieve recent balances with a validated start date, and the command does not claim unsupported end-date filtering.
- [ ] A user can retrieve aggregate snapshots with a validated start/end range and optional supported account-type filter.
- [ ] A user can retrieve type-scoped snapshots with a validated start date and `month|year` timeframe; month values retain their documented `YYYY-MM` precision.
- [ ] Account-type filter validation reuses or coordinates with `mc-7xfl` rather than implementing a second discovery surface.
- [ ] A user can inspect aggregate refresh completion without initiating or waiting for a refresh; requested unknown account IDs produce an explicit unknown/not-found result rather than `complete: true`.
- [ ] One-sided or reversed ranges, invalid dates/timeframes/types, empty identifiers, and unknown requested accounts fail deterministically before the target API call.
- [ ] Hidden, deactivated, manual, asset, and liability accounts are deliberately represented; directly identified hidden/deactivated accounts remain inspectable.
- [ ] Missing balances and sparse histories remain `null`/empty rather than becoming fabricated zero values.
- [ ] Normalized outputs have documented stable shapes; explicit raw mode preserves each single upstream response without normalization.
- [ ] Commands use shared date, adapter, service, transformer, execution, and output boundaries; command handlers do not import or interpret upstream client details directly.
- [ ] Every command added here is classified `read_only`; no polling or refresh mutation is added or changed.
- [ ] Unit/CLI tests verify API mapping, method-specific date behavior, unknown refresh IDs, null/empty responses, hidden/manual accounts, and output formats.
- [ ] The required upstream-client compatibility floor is verified, user-facing documentation is complete, and repository verification passes.

