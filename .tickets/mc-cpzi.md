---
id: mc-cpzi
status: open
deps: [mc-cd12, mc-h3cl]
links: []
created: 2026-09-11T01:47:48Z
type: feature
priority: 2
assignee: cc-vps
parent: mc-cr09
tags: [p3, schemas, contracts, documentation, automation]
---
# Publish tested machine-readable output schemas

Make normalized CLI output contracts directly consumable by users, agents, and integration tooling. Examples and prose alone do not precisely communicate required fields, nullability, nested structures, enums, or compatibility expectations. Published schemas enable validation, generated documentation, fixtures, and safer downstream upgrades.

## Design

Choose a standard machine-readable schema format and a maintainable source of truth for stable normalized resources, mutation envelopes, and structured errors. Generated artifacts must not drift from runtime serializers and contract tests. Define contract versioning and compatibility rules for additive fields, removals, type changes, nullability changes, and raw passthrough output. Scope initial coverage to established public contracts and provide a clear extension path rather than attempting to describe arbitrary upstream raw payloads.

## Acceptance Criteria

- [ ] Versioned machine-readable schemas are published for the established normalized account and transaction outputs, structured errors, and shared mutation envelopes when available.
- [ ] Each schema defines required fields, types, nullability, nested objects/arrays, and enums without claiming guarantees for raw passthrough data.
- [ ] A documented compatibility policy distinguishes additive and breaking schema changes.
- [ ] CI validates schema files and proves representative runtime output/fixtures conform to them.
- [ ] Schema artifacts are deterministic and generated or checked from a single maintainable source of truth.
- [ ] Invalid representative payloads are rejected in negative tests so validation cannot pass vacuously.
- [ ] Schema identifiers and versions can be referenced by capabilities or external tooling without relying on repository paths.
- [ ] Documentation explains how consumers find, validate against, and migrate between schemas.
- [ ] Repository verification passes.

