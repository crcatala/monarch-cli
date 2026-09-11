---
id: mc-ppai
status: open
deps: [mc-h3cl]
links: []
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, investments, holdings, read-only, normalization]
---
# Add normalized investment holdings views

Give users a useful portfolio view across investment accounts rather than requiring them to understand nested API payloads or query each account manually. This enables portfolio inventory, account-level inspection, and allocation analysis while remaining read-only.

## Design

Create an investment-focused service and command surface that can discover eligible accounts, fetch holdings efficiently, normalize security and value fields, and optionally aggregate the same holding across accounts. Avoid duplicating account-history commands. Preserve source account context in non-aggregated output, define the grouping key and limitations for aggregation, and avoid unbounded sequential API calls. Keep upstream-client details behind the adapter/service boundary.

## Acceptance Criteria

- [ ] Users can list normalized holdings across eligible investment accounts.
- [ ] Users can restrict holdings to one or more account IDs.
- [ ] Hidden-account inclusion behavior is explicit and defaults safely.
- [ ] Non-aggregated rows retain source account identity and relevant security identifiers.
- [ ] Optional aggregation has a documented deterministic grouping key and reports how many accounts contributed.
- [ ] Missing ticker, security metadata, quantity, basis, price, or value fields do not crash the command or create misleading values.
- [ ] Multi-account retrieval uses a bounded, tested strategy and avoids unnecessary repeated account discovery.
- [ ] JSON, table/plain, empty-result, and optional raw output behavior are tested.
- [ ] The implementation respects adapter/service/transformer boundaries and does not add direct upstream imports to command handlers.
- [ ] User-facing documentation and repository verification are complete.

