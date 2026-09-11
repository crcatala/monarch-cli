---
id: mc-8dfd
status: open
deps: [mc-hszv]
links: []
created: 2026-09-11T01:36:40Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p2, accounts, transactions, household, ownership, read-only]
---
# Expose household ownership in account and transaction output

Make ownership attribution visible for shared households. Account and transaction records may belong to or be assigned to a specific household member, but dropping that metadata from normalized CLI output prevents users and automated workflows from separating activity by person, explaining shared records, or safely selecting records for later actions.

This ticket is read-only: it establishes clear ownership semantics in the stable output contract. Changing ownership is outside scope until a supported mutation workflow is designed separately.

## Design

Model ownership as an optional relationship at the normalization boundary. Preserve both a stable identifier and a display value when available, and distinguish unavailable/unassigned/shared ownership from malformed data without inventing an owner. Account and transaction representations should use consistent naming and null semantics where the underlying concepts align.

Review the impact on compact, table/plain, JSON, CSV, quiet, and raw output. Raw output must remain untouched. Keep household-specific upstream response shapes behind adapters/services and transformers rather than branching in command handlers.

## Acceptance Criteria

- [ ] Normalized account output exposes optional owner identity using documented stable fields.
- [ ] Normalized transaction list and detail output expose optional owner identity and ownership-override metadata where available.
- [ ] Unassigned, shared, unavailable, null, and partially populated owner data have explicit non-misleading semantics.
- [ ] Account and transaction fields use a consistent naming convention without collapsing distinct domain meanings.
- [ ] Existing normalized fields remain backward compatible and raw output remains unmodified.
- [ ] Human-readable formats include ownership only where it remains useful and legible; machine-readable formats preserve stable values.
- [ ] No command added or changed by this ticket mutates ownership or any remote state.
- [ ] Unit and CLI tests cover complete, null, missing, shared/unassigned, and malformed nested owner payloads for accounts and transactions.
- [ ] The required upstream-client compatibility floor is declared and covered by clean-install/contract verification.
- [ ] Output-contract documentation is updated and repository verification passes.
