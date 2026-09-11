---
id: mc-4edf
status: open
deps: [mc-h3cl]
links: []
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

Build a coherent account-oriented read surface for account history, recent balances, aggregate or type-scoped snapshots, refresh status, and account-type discovery where supported. Decide command names and hierarchy from the domain model rather than mirroring upstream method names. Reuse shared date parsing, validation, adapter, and output layers. Refresh initiation is state-changing and is outside this read-only ticket unless it is already covered by the centralized mutation policy.

## Acceptance Criteria

- [ ] Users can retrieve balance history for a specific account.
- [ ] Users can retrieve recent balance data and net-worth/account snapshots over a validated date range.
- [ ] Users can inspect account refresh completion/status without initiating a refresh.
- [ ] Supported account types and subtypes can be discovered if the API exposes them reliably.
- [ ] Date, timeframe, account-type, and identifier validation is consistent with shared CLI conventions.
- [ ] Normalized output has a documented stable shape; raw output is opt-in where useful.
- [ ] Empty, null, hidden, manual, asset, and liability account cases are handled deliberately.
- [ ] No new command in this ticket changes remote state.
- [ ] Unit/CLI tests verify API mapping, date boundaries, null/empty responses, and output formats.
- [ ] User-facing documentation and repository verification are complete.

