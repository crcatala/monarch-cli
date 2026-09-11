---
id: mc-cpzi
status: open
deps: [mc-cd12, mc-h3cl, mc-ik8o]
links: [mc-82kf]
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

Publish JSON Schema Draft 2020-12 artifacts for established normalized account and transaction outputs, the structured error contract, and `mutation-outcome.v1`. Arbitrary raw passthrough payloads are explicitly unschematized and unstable.

Checked-in schema files are the normative contract for this initial implementation and are included as package resources in the wheel. Each has a stable URN identifier such as `urn:monarch-cli:schema:account:v1`, independent of repository paths. An ordinary module-level mapping resolves public contract names and versions to packaged artifacts; it is not a separately serialized subsystem. `mc-82kf` consumes the same mapping for capability discovery.

Use a development/test-only JSON Schema validator; do not add a schema-modeling runtime dependency or refactor transformers into a second object system. Existing contract tests become consumers of the published schemas. CI validates representative runtime transformer/error/mutation fixtures, rejects representative invalid payloads, and detects undocumented stable output fields without maintaining a parallel contract definition.

Schemas encode the post-`mc-h3cl` normalization semantics and the exact mutation envelope established by `mc-ik8o`. Unknown additive upstream fields remain irrelevant to normalized contracts. Schema changes follow a documented policy: optional additive properties and new open error codes may be additive; removals, required-field additions, type/nullability changes, and closed-enum semantic changes require a new schema version.

## Key Decisions

- **JSON Schema Draft 2020-12.** Use a widely supported validation standard.
- **Checked-in packaged artifacts are normative.** Runtime fixtures and existing contract tests validate against them.
- **Stable URN identifiers.** Consumers and capabilities never depend on repository paths.
- **No runtime modeling dependency.** Validation tooling remains development/test-only.
- **Raw output is excluded.** The CLI does not claim a stable contract for upstream passthrough payloads.
- **One lightweight contract mapping.** Schema lookup and capability references share an ordinary module-level mapping, not a separately serialized registry service.

## Acceptance Criteria

- [ ] Valid JSON Schema Draft 2020-12 artifacts are published for normalized account output, normalized transaction list/detail output, structured errors, and `mutation-outcome.v1`.
- [ ] Every schema defines required fields, types, nullability, nested objects/arrays, and closed enums where the CLI actually guarantees them.
- [ ] Raw passthrough output is explicitly excluded and documented as unstable.
- [ ] Every artifact has a stable versioned URN `$id` and is included in source distributions and wheels as a package resource.
- [ ] A module-level mapping resolves public contract name/version and URN to the packaged artifact; capabilities use that mapping rather than duplicate constants.
- [ ] Existing `tests/test_schemas.py` contracts validate representative runtime output against the published artifacts instead of maintaining a second independent field list.
- [ ] CI proves representative account, transaction, error, and mutation outputs conform and fails on undocumented stable fields or removals without maintaining a second field-list contract.
- [ ] Negative fixtures fail for missing required fields, wrong types, invalid nullability, impossible mutation summary counts, and invalid closed-enum values so validation cannot pass vacuously.
- [ ] A documented compatibility policy classifies optional additions and open error-code additions separately from removals, required-field additions, type/nullability changes, and closed-enum changes.
- [ ] Documentation explains how consumers locate packaged schemas, resolve stable IDs, validate output, and migrate between versions.
- [ ] No runtime schema/modeling dependency is introduced; repository verification and wheel smoke installation pass.
