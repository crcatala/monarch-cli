---
id: mc-h3cl
status: open
deps: [mc-43s0]
links: [mc-cd12, mc-c165]
created: 2026-09-11T01:21:50Z
type: feature
priority: 1
assignee: cc-vps
parent: mc-cr09
tags: [p1, architecture, transformers, api-contract, reliability]
---
# Harden normalization at upstream API boundaries

Make read-only and future mutation commands resilient to incomplete, nullable, or evolving API response shapes. External financial APIs may return null nested objects, omit optional collections, or add fields over time. Commands should not crash merely because an optional merchant, category, account, institution, or similar relationship is absent. A dependable normalization boundary enables a stable CLI contract for humans, scripts, and agents while keeping upstream response quirks out of presentation code.

## Design

Review the existing adapter, transformer, service, and output boundaries before choosing where normalization belongs. Prefer small reusable normalizers or domain transformers over scattered defensive access in command functions. Preserve raw-output behavior separately from the stable normalized contract. Treat additive stable fields deliberately and document defaults for absent values; do not silently invent financially meaningful values. Coordinate with existing transformer and schema-contract test tickets rather than duplicating their general test-infrastructure scope.

## Acceptance Criteria

- [ ] Existing account and transaction normalization handles null or missing nested objects without raising exceptions.
- [ ] Optional collection containers and result lists safely normalize when absent or null.
- [ ] Stable output fields have documented behavior for unavailable values.
- [ ] Raw output, where supported, remains unmodified and clearly distinct from normalized output.
- [ ] Normalization logic is located at an explicit boundary and is not duplicated across command handlers.
- [ ] Focused unit tests cover null, missing, empty, and representative complete payloads.
- [ ] Existing normalized field names and semantics remain backward compatible unless a change is explicitly documented.
- [ ] Repository verification passes.

