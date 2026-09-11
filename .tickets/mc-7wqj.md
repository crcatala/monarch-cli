---
id: mc-7wqj
status: open
deps: [mc-h3cl]
links: [mc-4edf, mc-kzp9, mc-nbvi, mc-oqc9]
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, reporting, cashflow, read-only]
---
# Add normalized cashflow detail

Expose category, category-group, merchant, and overall cashflow detail beyond the existing summary while preserving one clear cashflow-domain command surface.

## Design

Add `cashflow detail` under the existing cashflow group using the released upstream `get_cashflow` method. The response contains category, category-group, merchant, and overall summary blocks. Normalize those blocks into a stable documented contract without duplicating transaction summary, recurring activity, institution, subscription, or credit-history work now owned by `mc-nbvi`, `mc-oqc9`, and `mc-kzp9`.

Use the shared date parser and require both explicit bounds or neither, with `start <= end`. Presets resolve through the same conventions as `cashflow summary`. The upstream method accepts a `limit` argument that is not used for pagination by its aggregate query, so do not expose or document pagination that does not exist.

The detail response already includes the same overall summary concepts as the existing `cashflow summary` command. Reuse one summary normalizer so both commands have aligned field names and semantics; do not issue a second summary request from `cashflow detail`.

## Key Decisions

- **One cashflow-focused PR.** Other reporting and service domains were split into separate tickets.
- **No fictional pagination.** Aggregate detail is returned as one response.
- **Summary semantics are shared.** Existing summary and detail normalization must not drift.

## Acceptance Criteria

- [ ] `cashflow detail` returns normalized category, category-group, merchant, and overall summary data for the default period.
- [ ] Explicit start/end dates and shared presets are supported with the same inclusive-bound semantics as `cashflow summary`.
- [ ] One-sided ranges, invalid dates, and `start > end` fail before client creation or an API request.
- [ ] The command does not expose a pagination or limit option unsupported by the actual aggregate query.
- [ ] Overall summary fields reuse the existing cashflow summary normalization and do not require an additional API request.
- [ ] Null, empty, partial, and unavailable nested aggregate blocks produce stable non-misleading output under the `mc-h3cl` normalization rules.
- [ ] Normalized JSON and human-readable output have documented stable shapes; explicit raw mode preserves the upstream response.
- [ ] The command is classified read-only and performs no remote mutation.
- [ ] Unit/CLI tests verify API mapping, default and explicit date behavior, presets, validation-before-call, null/empty payloads, output contracts, and errors.
- [ ] User-facing documentation and repository verification are complete.

