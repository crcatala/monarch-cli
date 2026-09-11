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

Checked-in schema files are the normative contract for this initial implementation and are included as package resources in the wheel. Each has a stable URN identifier such as `urn:monarch-cli:schema:account:v1`, independent of repository paths. A small shared registry maps public contract names and versions to packaged artifacts; `mc-82kf` consumes this registry for capability discovery.

Use a development/test-only JSON Schema validator; do not add a schema-modeling runtime dependency or refactor transformers into a second object system. Existing contract tests become consumers of the published schemas. CI validates representative runtime transformer/error/mutation fixtures against the schemas, rejects representative invalid payloads, and checks schema keys against stable serializer output so prose tests and schema files cannot drift independently.

Schemas encode the post-`mc-h3cl` normalization semantics and the exact mutation envelope established by `mc-ik8o`. Unknown additive upstream fields remain irrelevant to normalized contracts. Schema changes follow a documented policy: optional additive properties and new open error codes may be additive; removals, required-field additions, type/nullability changes, and closed-enum semantic changes require a new schema version.

## Key Decisions

- **JSON Schema Draft 2020-12.** Use a widely supported validation standard.
- **Checked-in packaged artifacts are normative.** Runtime fixtures and existing contract tests validate against them.
- **Stable URN identifiers.** Consumers and capabilities never depend on repository paths.
- **No runtime modeling dependency.** Validation tooling remains development/test-only.
- **Raw output is excluded.** The CLI does not claim a stable contract for upstream passthrough payloads.
- **One contract registry.** Schema lookup and capability references use the same names and versions.

## Acceptance Criteria

- [ ] Valid JSON Schema Draft 2020-12 artifacts are published for normalized account output, normalized transaction list/detail output, structured errors, and `mutation-outcome.v1`.
- [ ] Every schema defines required fields, types, nullability, nested objects/arrays, and closed enums where the CLI actually guarantees them.
- [ ] Raw passthrough output is explicitly excluded and documented as unstable.
- [ ] Every artifact has a stable versioned URN `$id` and is included in source distributions and wheels as a package resource.
- [ ] A shared registry resolves public contract name/version and URN to the packaged artifact; capabilities use that registry rather than duplicate constants.
- [ ] Existing `tests/test_schemas.py` contracts validate representative runtime output against the published artifacts instead of maintaining a second independent field list.
- [ ] CI validates all schema files and proves representative account, transaction, error, and mutation outputs conform.
- [ ] Negative fixtures fail for missing required fields, wrong types, invalid nullability, impossible mutation summary counts, and invalid closed-enum values so validation cannot pass vacuously.
- [ ] Drift tests compare stable serializer/transformer keys with schema properties and fail on undocumented additions or removals.
- [ ] Artifacts and registry serialization are deterministic across repeated generation/verification runs.
- [ ] A documented compatibility policy classifies optional additions and open error-code additions separately from removals, required-field additions, type/nullability changes, and closed-enum changes.
- [ ] Documentation explains how consumers locate packaged schemas, resolve stable IDs, validate output, and migrate between versions.
- [ ] No runtime schema/modeling dependency is introduced; repository verification and wheel smoke installation pass.
