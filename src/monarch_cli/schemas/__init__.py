"""Published machine-readable output schemas (mc-cpzi).

Checked-in JSON Schema Draft 2020-12 artifacts under this package are the
normative contract for the CLI's stable normalized outputs. They ship in the
source distribution and wheel as package resources and each carries a stable,
versioned URN ``$id`` (for example ``urn:monarch-cli:schema:account:v1``)
independent of repository paths.

This module is the single lightweight contract mapping:

* :data:`SCHEMA_ARTIFACTS` resolves a public contract name and version to its
  packaged artifact, and :data:`SCHEMA_ARTIFACTS_BY_URN` resolves a stable URN
  to the same artifact.
* :data:`OPERATION_CONTRACTS` resolves a stable ``mutation-outcome.v1``
  operation identifier to its outcome schema and its ordered effect-entity
  identifiers. ``mc-82kf`` consumes this mapping for capability discovery
  rather than duplicating schema constants.

Raw passthrough output is deliberately excluded: it preserves upstream shapes
and is explicitly unstable, so it has no published schema.

JSON Schema validation is a development/test-only concern; this module uses
only the standard library and adds no runtime schema or modeling dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, cast

#: Package holding the checked-in schema artifacts as package resources.
_PACKAGE = "monarch_cli.schemas"


@dataclass(frozen=True)
class SchemaArtifact:
    """One published, versioned schema artifact.

    Attributes:
        contract: Public contract name (for example ``account``).
        version: Contract version (for example ``v1``).
        urn: Stable versioned URN used as the artifact ``$id``.
        resource: File name of the packaged artifact within this package.
    """

    contract: str
    version: str
    urn: str
    resource: str

    def read_text(self) -> str:
        """Return the artifact JSON text from the packaged resource."""
        return resources.files(_PACKAGE).joinpath(self.resource).read_text(encoding="utf-8")

    def load(self) -> dict[str, Any]:
        """Return the parsed artifact as a JSON object."""
        return cast("dict[str, Any]", json.loads(self.read_text()))


def _artifact(contract: str, version: str, resource: str) -> SchemaArtifact:
    return SchemaArtifact(
        contract=contract,
        version=version,
        urn=f"urn:monarch-cli:schema:{contract}:{version}",
        resource=resource,
    )


#: Public contract name/version -> packaged artifact. The normative mapping.
SCHEMA_ARTIFACTS: dict[tuple[str, str], SchemaArtifact] = {
    ("account", "v1"): _artifact("account", "v1", "account.v1.json"),
    ("transaction", "v1"): _artifact("transaction", "v1", "transaction.v1.json"),
    ("transaction-detail", "v1"): _artifact(
        "transaction-detail", "v1", "transaction-detail.v1.json"
    ),
    ("error", "v1"): _artifact("error", "v1", "error.v1.json"),
    ("mutation-outcome", "v1"): _artifact("mutation-outcome", "v1", "mutation-outcome.v1.json"),
}

#: Stable URN -> packaged artifact.
SCHEMA_ARTIFACTS_BY_URN: dict[str, SchemaArtifact] = {
    artifact.urn: artifact for artifact in SCHEMA_ARTIFACTS.values()
}

#: Stable effect-entity identifiers for the multi-stage attachment workflow.
#: Selected by ``mc-2v9a`` and shared here so no command-local attachment
#: schema constant is duplicated.
ATTACHMENT_MEDIA_ENTITY = "attachment_media"
ATTACHMENT_ENTITY = "attachment"


@dataclass(frozen=True)
class OperationContract:
    """Schema and stable effect entities for one mutation operation.

    Attributes:
        operation: Stable ``mutation-outcome.v1`` operation identifier.
        schema_contract: Public contract name of the outcome schema.
        effect_entities: Ordered stable effect-entity identifiers the operation
            can emit as outcome item ``entity`` values.
    """

    operation: str
    schema_contract: str
    effect_entities: tuple[str, ...]


_OPERATION_ENTITIES: dict[str, tuple[str, ...]] = {
    "accounts.refresh": ("account",),
    "transactions.update": ("transaction",),
    "transactions.batch-update": ("transaction",),
    "transactions.create": ("transaction",),
    "transactions.delete": ("transaction",),
    "transactions.tags.create": ("tag",),
    "transactions.tags.replace": ("transaction",),
    "transactions.tags.add": ("transaction",),
    "transactions.tags.clear": ("transaction",),
    "transactions.splits.replace": ("transaction",),
    "transactions.splits.clear": ("transaction",),
    "transactions.attachments.add": (ATTACHMENT_MEDIA_ENTITY, ATTACHMENT_ENTITY),
    "transactions.review.mark": ("transaction",),
    "transactions.review.return": ("transaction",),
    "budgets.set": ("budget",),
    # Test-only disposable-fixture operations (mc-584r) are real remote effects
    # that emit the same envelope; they are never exposed as public commands.
    "live-fixture.account.create": ("account",),
    "live-fixture.transaction.create": ("transaction",),
    "live-fixture.transaction.delete": ("transaction",),
    "live-fixture.account.delete": ("account",),
}

#: Stable operation identifier -> operation contract.
OPERATION_CONTRACTS: dict[str, OperationContract] = {
    operation: OperationContract(
        operation=operation,
        schema_contract="mutation-outcome",
        effect_entities=entities,
    )
    for operation, entities in _OPERATION_ENTITIES.items()
}


def schema_artifact(contract: str, version: str = "v1") -> SchemaArtifact:
    """Resolve a public contract name/version to its packaged artifact.

    Args:
        contract: Public contract name (for example ``account``).
        version: Contract version (defaults to ``v1``).

    Returns:
        The matching :class:`SchemaArtifact`.

    Raises:
        KeyError: If the contract name/version is not published.
    """
    try:
        return SCHEMA_ARTIFACTS[(contract, version)]
    except KeyError:
        known = sorted(f"{name}:{ver}" for name, ver in SCHEMA_ARTIFACTS)
        raise KeyError(
            f"Unknown schema contract '{contract}' version '{version}'. Known: {known}"
        ) from None


def schema_artifact_by_urn(urn: str) -> SchemaArtifact:
    """Resolve a stable schema URN to its packaged artifact.

    Args:
        urn: Stable versioned URN (for example ``urn:monarch-cli:schema:account:v1``).

    Returns:
        The matching :class:`SchemaArtifact`.

    Raises:
        KeyError: If the URN is not published.
    """
    try:
        return SCHEMA_ARTIFACTS_BY_URN[urn]
    except KeyError:
        raise KeyError(f"Unknown schema URN '{urn}'.") from None


def load_schema(contract: str, version: str = "v1") -> dict[str, Any]:
    """Return the parsed published schema for a public contract name/version."""
    return schema_artifact(contract, version).load()


def operation_contract(operation: str) -> OperationContract:
    """Resolve a stable operation identifier to its schema and effect entities.

    Args:
        operation: Stable ``mutation-outcome.v1`` operation identifier.

    Returns:
        The matching :class:`OperationContract`.

    Raises:
        KeyError: If the operation is not registered.
    """
    try:
        return OPERATION_CONTRACTS[operation]
    except KeyError:
        raise KeyError(f"Unknown mutation operation '{operation}'.") from None


__all__ = [
    "ATTACHMENT_ENTITY",
    "ATTACHMENT_MEDIA_ENTITY",
    "OPERATION_CONTRACTS",
    "SCHEMA_ARTIFACTS",
    "SCHEMA_ARTIFACTS_BY_URN",
    "OperationContract",
    "SchemaArtifact",
    "load_schema",
    "operation_contract",
    "schema_artifact",
    "schema_artifact_by_urn",
]
