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

Make ownership attribution visible for shared households. Account and transaction records may be assigned to a household member, but dropping that relationship from normalized CLI output prevents users and automated workflows from separating activity by person, explaining records, or safely selecting records for later actions.

This ticket is read-only. Changing ownership remains outside scope until a supported mutation workflow is designed separately.

## Design

Normalize the optional upstream `ownedByUser` relationship consistently across accounts and transactions. Expose stable `owner_id` and `owner_name` fields; adapt the upstream account `displayName` and transaction `name` variants at the transformer boundary. Transactions additionally expose `ownership_overridden_at` when returned upstream.

A missing, null, or malformed owner relationship produces null normalized owner fields. It must not be labeled “shared” or “unassigned,” because the released upstream response has no field that distinguishes those meanings. Likewise, `ownership_overridden_at` proves only that an override timestamp exists; it does not identify the actor, previous owner, or direction of reassignment.

Review compact, table/plain, JSON, CSV, quiet, and raw output deliberately. Machine-readable normalized formats preserve stable owner fields. Human formats may show a concise owner name where legible; quiet remains ID-only. Raw output remains untouched. Keep upstream shape differences behind services/transformers rather than command-handler branches.

## Key Decisions

- **No invented shared state.** Null owner fields mean only that owner identity was not provided by the upstream response.
- **One normalized naming convention.** Account `displayName` and transaction `name` both map to `owner_name`.
- **Override metadata remains literal.** Expose the timestamp without inferring who changed ownership or what it changed from.
- **Read-only scope.** This ticket neither mutates ownership nor adds remote state changes.

## Acceptance Criteria

- [ ] Normalized account output always includes nullable `owner_id` and `owner_name` fields sourced from `ownedByUser.id` and `ownedByUser.displayName` when valid.
- [ ] Normalized transaction list and detail output always include nullable `owner_id`, `owner_name`, and `ownership_overridden_at` fields when available.
- [ ] Missing, null, non-object, and partially populated owner payloads produce documented null fields or typed malformed-payload handling without crashes or invented identities.
- [ ] Documentation states that null ownership does not distinguish shared, unassigned, unavailable, or unsupported upstream states.
- [ ] Account and transaction outputs use the same public owner naming despite their different upstream display-field names.
- [ ] Existing normalized fields remain backward compatible and raw output remains byte-for-structure unmodified.
- [ ] JSON and CSV preserve stable owner values; table/plain/compact add only a concise useful owner display; quiet remains ID-only.
- [ ] No command added or changed by this ticket mutates ownership or any remote state.
- [ ] Unit and CLI tests cover complete, null, missing, non-object, and partially populated owner payloads for account list, transaction list, and transaction detail.
- [ ] Tests prove `ownership_overridden_at` is passed through without deriving an actor, previous owner, or boolean shared state.
- [ ] The required upstream-client compatibility floor is declared and covered by clean-install/contract verification.
- [ ] Output-contract documentation is updated and repository verification passes.
