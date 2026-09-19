# Machine-readable output schemas

Monarch CLI publishes checked-in **JSON Schema Draft 2020-12** artifacts for
its stable normalized output. They are the normative contract that consumers,
agents, and integration tooling can validate against — examples and prose alone
cannot precisely communicate required fields, nullability, nested structures,
enums, or compatibility expectations.

Raw passthrough output (`--raw`) preserves upstream shapes and is **explicitly
unschematized and unstable**; it has no published schema.

## Published contracts

| Contract | Version | Stable URN (`$id`) | Packaged resource |
|---|---|---|---|
| Normalized account | v1 | `urn:monarch-cli:schema:account:v1` | `account.v1.json` |
| Normalized transaction (list record) | v1 | `urn:monarch-cli:schema:transaction:v1` | `transaction.v1.json` |
| Normalized transaction detail | v1 | `urn:monarch-cli:schema:transaction-detail:v1` | `transaction-detail.v1.json` |
| Structured error | v1 | `urn:monarch-cli:schema:error:v1` | `error.v1.json` |
| Mutation outcome | v1 | `urn:monarch-cli:schema:mutation-outcome:v1` | `mutation-outcome.v1.json` |

The structured error artifact covers the error object emitted on stderr for
pre-execution validation, authorization, and read failures
(`MonarchCLIError.to_dict()`). The mutation outcome artifact covers the
`mutation-outcome.v1` envelope emitted on stdout after a remote write is
attempted; dry-run previews (`status: "dry_run"`) are deliberately **not** part
of that schema family.

## Locating packaged schemas

The artifacts ship inside the installed package as package resources. Resolve
them through the module-level mapping rather than by repository path:

```python
from monarch_cli.schemas import load_schema, schema_artifact

artifact = schema_artifact("account")  # contract name; version defaults to v1
print(artifact.urn)  # urn:monarch-cli:schema:account:v1
document = artifact.load()  # parsed JSON Schema dict
text = artifact.read_text()  # raw JSON text
```

To locate the resource directory from an installed environment:

```python
from importlib import resources

schemas_dir = resources.files("monarch_cli.schemas")
print(schemas_dir)
```

`monarch_cli.schemas` uses only the standard library; validating output is a
consumer-side concern and the CLI adds **no runtime schema or modeling
dependency**.

## Resolving stable IDs

Every artifact carries a stable, versioned URN `$id` independent of repository
paths. Consumers should reference contracts by URN (or by contract name +
version) and should not depend on file locations:

```python
from monarch_cli.schemas import schema_artifact_by_urn

artifact = schema_artifact_by_urn("urn:monarch-cli:schema:mutation-outcome:v1")
```

## Validating output

Any Draft 2020-12 validator works. Example with the development/test-only
`jsonschema` package:

```python
from jsonschema import Draft202012Validator
from monarch_cli.schemas import load_schema

validator = Draft202012Validator(load_schema("account"))
validator.validate(record)  # raises jsonschema.ValidationError on mismatch
```

Schemas use `additionalProperties: false` on stable normalized records, so an
undocumented field is a validation error rather than silently ignored. The one
JSON Schema limitation is arithmetic: the mutation outcome's
`summary.total == len(items)` and per-status count invariants cannot be
expressed in Draft 2020-12; they are enforced by the CLI contract tests.

## Operation and effect-entity mapping

`monarch_cli.schemas.OPERATION_CONTRACTS` maps each stable operation identifier
to its outcome schema and its ordered effect-entity identifiers, for example:

```python
from monarch_cli.schemas import (
    ATTACHMENT_ENTITY,
    ATTACHMENT_MEDIA_ENTITY,
    operation_contract,
)

contract = operation_contract("transactions.attachments.add")
contract.schema_contract  # "mutation-outcome"
contract.effect_entities  # (ATTACHMENT_MEDIA_ENTITY, ATTACHMENT_ENTITY)
```

This is the shared mapping for schema identity and capability discovery
(`mc-82kf`); commands and capability output consume it instead of duplicating
schema or entity constants.

## Compatibility policy

| Change | Classification | Version effect |
|---|---|---|
| New **optional** property on a record/envelope | Additive | No version change |
| New **open** error code (`error.code`, item `error.code`) | Additive | No version change |
| New optional key inside `result` / `error.details` | Additive | No version change |
| New operation or effect-entity identifier | Additive | No version change |
| Removing or renaming any property | Breaking | New schema version |
| Adding a **required** property | Breaking | New schema version |
| Narrowing nullability or changing a property type | Breaking | New schema version |
| Changing a **closed enum** value or its semantics | Breaking | New schema version |
| Changing a top-level status meaning or exit-code mapping | Breaking | New schema version |

In short: **optional additive properties and new open error codes are additive;
removals, required-field additions, type/nullability changes, and closed-enum
changes require a new schema version.**

## Migrating between versions

- A new version is published as a new URN (for example
  `urn:monarch-cli:schema:mutation-outcome:v2`). The previous version remains
  available so consumers can migrate on their own schedule.
- Pin the contract URN (or contract name + version) you consume; do not depend
  on "latest".
- Migration notes are recorded in [CHANGELOG](../CHANGELOG.md) and, for
  larger changes, under [docs/migrations/](migrations/).
- The compatibility policy above defines which changes require a new version,
  so a version bump is the reliable signal that a consumer must re-read the
  schema and adjust.

Because additive optional properties intentionally **do not** bump the version,
a version bump alone is not sufficient notice. Resolving a pinned URN (or
contract name + version) through `monarch_cli.schemas` always returns the
**current** artifact, which already includes newly added optional properties.
Consumers who vendor or copy the JSON into their own repository must refresh
that copy: normalized records use `additionalProperties: false`, so an older
vendored artifact rejects fields added after it was copied even when the change
was additive.

## Relationship to runtime contracts

The runtime behavior is documented in
[Output contracts](output-contracts.md) and
[Mutation outcomes](mutation-outcomes.md). The published schemas are the
machine-readable form of those contracts, and `tests/test_schemas.py` validates
representative runtime output against them so the schemas and the CLI cannot
drift apart.
