"""Deterministic CLI capabilities manifest (mc-82kf).

The ``monarch capabilities`` command emits one versioned JSON document that
lets automation discover the installed CLI without scraping styled help text:
command paths, arguments, options, required inputs, defaults, output support,
safety requirements, interactivity, and the published contract versions.

Two facts drive the design:

* **Explicit metadata owns behavior.** :data:`COMMAND_CAPABILITIES` is the
  authoritative registry of every registered command's effects, safety policy,
  interactivity, preview support, and output support. None of those
  properties is inferred from a command, framework, upstream method, or
  GraphQL name.
* **Framework introspection discovers syntax only.** Typer is used solely to
  enumerate registered command paths, arguments, and options; their
  representation here is a plain, stable projection that never exposes
  framework-internal object shapes.

Stable schema identifiers and contract versions come from the shared
``monarch_cli.schemas`` mapping published by ``mc-cpzi``; this module consumes
it rather than duplicating schema constants. Raw passthrough output is
explicitly unstable and unschematized.

Generating the manifest performs no authentication lookup, client
construction, network request, prompt, config/session creation or write, or
other local/remote mutation: :func:`build_capabilities_manifest` only reads
process-local registration metadata and the checked-in schema mapping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import typer.main

from ..schemas import OPERATION_CONTRACTS, SCHEMA_ARTIFACTS, SCHEMA_ARTIFACTS_BY_URN
from .config import VALID_FORMATS
from .operations import Effect, collect_command_effects

#: Version of the manifest envelope itself. A breaking shape change requires a
#: new version; additive optional keys do not.
CAPABILITIES_MANIFEST_VERSION = "capabilities.v1"

#: Version of the classification taxonomy (the shared :class:`Effect` members
#: plus the explicit safety flags). New ``Effect`` members extend the taxonomy
#: additively and appear automatically in every emitted manifest.
CAPABILITIES_TAXONOMY_VERSION = "capabilities-taxonomy.v1"

#: Global rendering formats selectable with ``--format`` / ``--json``.
GLOBAL_FORMATS: tuple[str, ...] = tuple(VALID_FORMATS)

#: Stable URN for the mutation outcome envelope, consumed by every remote
#: mutation command. Resolved from the ``mc-cpzi`` mapping, never duplicated.
MUTATION_OUTCOME_URN = SCHEMA_ARTIFACTS[("mutation-outcome", "v1")].urn
ACCOUNT_URN = SCHEMA_ARTIFACTS[("account", "v1")].urn
TRANSACTION_URN = SCHEMA_ARTIFACTS[("transaction", "v1")].urn
TRANSACTION_DETAIL_URN = SCHEMA_ARTIFACTS[("transaction-detail", "v1")].urn
ERROR_URN = SCHEMA_ARTIFACTS[("error", "v1")].urn


class CapabilitiesError(Exception):
    """The registered command tree and the explicit metadata disagree.

    This is a programming error: a registered command lacks capability
    metadata, the metadata references an operations-policy mismatch or an
    unknown schema, or the generated inventory is unexpectedly empty. It must
    fail loudly rather than emit a partial manifest.
    """


@dataclass(frozen=True)
class OutputCapability:
    """Explicit output support for one command.

    ``stable_normalized`` marks output that is part of a stable contract;
    ``raw`` marks the explicitly unstable upstream passthrough, which has no
    schema. ``ndjson`` is per-command (never global). ``quiet`` marks commands
    whose records flow through the global ID-only ``--quiet`` behavior.
    """

    quiet: bool = True
    ndjson: bool = False
    raw: bool = False
    stable_normalized: bool = True
    schemas: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandCapability:
    """Explicit, authoritative metadata for one registered command."""

    path: str
    effects: frozenset[Effect]
    destructive: bool = False
    interactive: bool = False
    preview: bool = False
    output: OutputCapability = field(default_factory=OutputCapability)

    @property
    def requires_authorization(self) -> bool:
        """Remote mutations require per-invocation ``--allow-mutations``."""
        return Effect.REMOTE_MUTATION in self.effects


#: The complete reviewed command inventory. Every registered command must have
#: an entry here; :func:`validate_capabilities` fails when the registered tree
#: and this registry disagree.
COMMAND_CAPABILITIES: dict[str, CommandCapability] = {
    # --- auth ---------------------------------------------------------------
    "auth login": CommandCapability(
        "auth login",
        frozenset({Effect.REMOTE_AUTHENTICATION, Effect.LOCAL_CREDENTIAL_CHANGE}),
        interactive=True,
        output=OutputCapability(quiet=False, stable_normalized=False),
    ),
    "auth status": CommandCapability(
        "auth status",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(quiet=False),
    ),
    "auth logout": CommandCapability(
        "auth logout",
        frozenset({Effect.LOCAL_CREDENTIAL_CHANGE}),
        output=OutputCapability(quiet=False, stable_normalized=False),
    ),
    "auth doctor": CommandCapability(
        "auth doctor",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(quiet=False, stable_normalized=False),
    ),
    "auth ping": CommandCapability(
        "auth ping",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(quiet=False),
    ),
    "auth setup": CommandCapability(
        "auth setup",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(quiet=False, stable_normalized=False),
    ),
    # --- accounts -----------------------------------------------------------
    "accounts list": CommandCapability(
        "accounts list",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(ndjson=True, raw=True, schemas=(ACCOUNT_URN,)),
    ),
    "accounts types": CommandCapability(
        "accounts types",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "accounts history": CommandCapability(
        "accounts history",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "accounts recent-balances": CommandCapability(
        "accounts recent-balances",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "accounts snapshots": CommandCapability(
        "accounts snapshots",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "accounts snapshots-by-type": CommandCapability(
        "accounts snapshots-by-type",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "accounts refresh-status": CommandCapability(
        "accounts refresh-status",
        frozenset({Effect.READ_ONLY}),
    ),
    "accounts refresh": CommandCapability(
        "accounts refresh",
        frozenset({Effect.REMOTE_MUTATION}),
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    # --- transactions -------------------------------------------------------
    "transactions list": CommandCapability(
        "transactions list",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(ndjson=True, raw=True, schemas=(TRANSACTION_URN,)),
    ),
    "transactions summary": CommandCapability(
        "transactions summary",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "transactions recurring": CommandCapability(
        "transactions recurring",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "transactions get": CommandCapability(
        "transactions get",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True, schemas=(TRANSACTION_DETAIL_URN,)),
    ),
    "transactions update": CommandCapability(
        "transactions update",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions batch-update": CommandCapability(
        "transactions batch-update",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions create": CommandCapability(
        "transactions create",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions delete": CommandCapability(
        "transactions delete",
        frozenset({Effect.REMOTE_MUTATION}),
        destructive=True,
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions splits show": CommandCapability(
        "transactions splits show",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "transactions splits replace": CommandCapability(
        "transactions splits replace",
        frozenset({Effect.REMOTE_MUTATION}),
        destructive=True,
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions splits clear": CommandCapability(
        "transactions splits clear",
        frozenset({Effect.REMOTE_MUTATION}),
        destructive=True,
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions tags list": CommandCapability(
        "transactions tags list",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "transactions tags show": CommandCapability(
        "transactions tags show",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "transactions tags create": CommandCapability(
        "transactions tags create",
        frozenset({Effect.REMOTE_MUTATION}),
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions tags replace": CommandCapability(
        "transactions tags replace",
        frozenset({Effect.REMOTE_MUTATION}),
        destructive=True,
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions tags add": CommandCapability(
        "transactions tags add",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions tags clear": CommandCapability(
        "transactions tags clear",
        frozenset({Effect.REMOTE_MUTATION}),
        destructive=True,
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions attachments add": CommandCapability(
        "transactions attachments add",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions review mark": CommandCapability(
        "transactions review mark",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "transactions review return": CommandCapability(
        "transactions review return",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    # --- budgets / cashflow / categories / institutions / investments -------
    "budgets list": CommandCapability(
        "budgets list",
        frozenset({Effect.READ_ONLY}),
    ),
    "budgets set": CommandCapability(
        "budgets set",
        frozenset({Effect.REMOTE_MUTATION}),
        preview=True,
        output=OutputCapability(
            quiet=False, stable_normalized=True, schemas=(MUTATION_OUTCOME_URN,)
        ),
    ),
    "cashflow summary": CommandCapability(
        "cashflow summary",
        frozenset({Effect.READ_ONLY}),
    ),
    "cashflow detail": CommandCapability(
        "cashflow detail",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "categories list": CommandCapability(
        "categories list",
        frozenset({Effect.READ_ONLY}),
    ),
    "institutions list": CommandCapability(
        "institutions list",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "investments holdings": CommandCapability(
        "investments holdings",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    "subscription show": CommandCapability(
        "subscription show",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(raw=True),
    ),
    # --- capabilities -------------------------------------------------------
    "capabilities": CommandCapability(
        "capabilities",
        frozenset({Effect.READ_ONLY}),
        output=OutputCapability(quiet=False),
    ),
}

#: The public command that emits this manifest. It is self-describing: the
#: registry above contains an entry for it like every other command.
CAPABILITIES_COMMAND = "capabilities"


def _param_type(param: Any) -> tuple[str, list[str]]:
    """Project a Typer/Click parameter type into a stable (type, choices) pair.

    Never returns a framework type object; only plain strings leave this
    function so the manifest cannot expose framework-internal shapes.
    """
    choices = list(getattr(param.type, "choices", []) or [])
    if choices:
        return "enum", [str(choice) for choice in choices]
    name = str(getattr(param.type, "name", "")).lower()
    return {
        "text": "string",
        "integer": "integer",
        "int": "integer",
        "float": "number",
        "boolean": "boolean",
        "bool": "boolean",
        "path": "path",
        "filename": "path",
    }.get(name, "string"), []


def _project_param(param: Any) -> dict[str, Any]:
    """Project one Typer/Click parameter into a stable plain dictionary."""
    is_argument = getattr(param, "param_type_name", "") == "argument"
    type_name, choices = _param_type(param)
    default = getattr(param, "default", None)
    if default is None:
        default_repr: Any = None
    elif isinstance(default, bool | int | float):
        default_repr = default
    else:
        default_repr = str(default)
    return {
        "name": param.name,
        "kind": "argument" if is_argument else "option",
        "flags": [*getattr(param, "opts", []), *getattr(param, "secondary_opts", [])],
        "required": bool(getattr(param, "required", False)),
        "repeatable": bool(getattr(param, "multiple", False)),
        "type": type_name,
        "choices": choices,
        "default": default_repr,
    }


def _project_command(node: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (arguments, options) projections for one registered command."""
    arguments: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for param in node.params:
        projected = _project_param(param)
        if projected["kind"] == "argument":
            arguments.append(projected)
        else:
            options.append(projected)
    arguments.sort(key=lambda item: item["name"])
    options.sort(key=lambda item: item["name"])
    return arguments, options


def _walk_commands(node: Any, prefix: tuple[str, ...]) -> dict[tuple[str, ...], Any]:
    """Recursively collect ``path tuple -> registered command`` for a Typer app."""
    found: dict[tuple[str, ...], Any] = {}
    for name, child in getattr(node, "commands", {}).items():
        path = (*prefix, name)
        if hasattr(child, "commands"):
            found.update(_walk_commands(child, path))
        else:
            found[path] = child
    return found


def _schema_contract_entries() -> list[dict[str, str]]:
    """Published schema contracts from the ``mc-cpzi`` mapping, sorted."""
    return [
        {"contract": artifact.contract, "version": artifact.version, "urn": artifact.urn}
        for artifact in sorted(
            SCHEMA_ARTIFACTS.values(), key=lambda item: (item.contract, item.version)
        )
    ]


def _operation_contract_entries() -> list[dict[str, Any]]:
    """Operation -> outcome-schema/effect-entity mapping, sorted."""
    return [
        {
            "operation": contract.operation,
            "schema_urn": SCHEMA_ARTIFACTS[(contract.schema_contract, "v1")].urn,
            "effect_entities": list(contract.effect_entities),
        }
        for contract in sorted(OPERATION_CONTRACTS.values(), key=lambda item: item.operation)
    ]


def _verify_schema_urns(urn: str) -> str:
    if urn not in SCHEMA_ARTIFACTS_BY_URN:
        raise CapabilitiesError(f"Capability metadata references unknown schema URN '{urn}'.")
    return urn


def _global_output_section() -> dict[str, Any]:
    return {
        "formats": list(GLOBAL_FORMATS),
        "quiet": {
            "flag": "--quiet",
            "aliases": ["-q"],
            "behavior": "one ID per line",
            "mutation_outcomes_compatible": False,
        },
        "mutation_outcomes": {
            "format": "json",
            "schema_urn": MUTATION_OUTCOME_URN,
            "quiet_compatible": False,
        },
        "raw": {
            "stable": False,
            "schema_urn": None,
            "note": (
                "Raw passthrough preserves upstream shapes and is explicitly "
                "unschematized and unstable."
            ),
        },
        "error_schema_urn": ERROR_URN,
    }


def _safety_section() -> dict[str, Any]:
    return {
        "read_only_by_default": True,
        "authorization": {
            "flag": "--allow-mutations",
            "placement": "before the command path",
            "env_var": None,
            "config_key": None,
            "applies_to": [Effect.REMOTE_MUTATION.value],
            "grants": "remote mutations for this invocation only",
        },
        "destructive_confirmation": {
            "flag": "--yes",
            "config_key": "confirm_destructive",
            "authorizes_mutation": False,
        },
        "non_interactive": {
            "flag": "--non-interactive",
            "env_var": "MONARCH_NON_INTERACTIVE",
            "config_key": "non_interactive",
            "auto_answers_confirmation": False,
        },
    }


def _command_entry(
    path_tuple: tuple[str, ...],
    capability: CommandCapability,
    node: Any,
) -> dict[str, Any]:
    arguments, options = _project_command(node)
    return {
        "path": list(path_tuple),
        "name": capability.path,
        "effects": sorted(effect.value for effect in capability.effects),
        "safety": {
            "requires_authorization": capability.requires_authorization,
            "requires_destructive_confirmation": capability.destructive,
            "interactive": capability.interactive,
            "supports_preview": capability.preview,
        },
        "output": {
            "quiet": capability.output.quiet,
            "ndjson": capability.output.ndjson,
            "raw": capability.output.raw,
            "stable_normalized": capability.output.stable_normalized,
            "schemas": [_verify_schema_urns(urn) for urn in capability.output.schemas],
        },
        "arguments": arguments,
        "options": options,
    }


def _coerce_root_app(app: Any) -> Any:
    """Return the Click command tree for a Typer app or a Click command."""
    if hasattr(app, "registered_commands") or hasattr(app, "registered_groups"):
        return typer.main.get_command(app)
    return app


def validate_capabilities(app: Any) -> None:
    """Assert the registered command tree and explicit metadata agree.

    Raises:
        CapabilitiesError: If a registered command lacks metadata, the
            metadata names an unregistered command, a command's declared
            effects disagree with the shared execution policy, a preview
            declaration disagrees with the registered ``--dry-run`` option,
            an ``NDJSON``/raw declaration disagrees with the registered
            options, an unknown schema is referenced, or the inventory is
            empty.
    """
    root = _coerce_root_app(app)
    registered = _walk_commands(root, ())
    registry_paths = {
        tuple(capability.path.split()) for capability in COMMAND_CAPABILITIES.values()
    }
    registered_paths = set(registered)

    if not registered_paths:
        raise CapabilitiesError("Registered command inventory is unexpectedly empty.")

    missing = sorted(" ".join(path) for path in registered_paths - registry_paths)
    if missing:
        raise CapabilitiesError(
            "Registered commands are missing capability metadata: " + ", ".join(missing)
        )
    unknown = sorted(" ".join(path) for path in registry_paths - registered_paths)
    if unknown:
        raise CapabilitiesError(
            "Capability metadata names unregistered commands: " + ", ".join(unknown)
        )

    policy = collect_command_effects(app)
    for name, capability in COMMAND_CAPABILITIES.items():
        if policy.get(name) != capability.effects:
            raise CapabilitiesError(
                f"Capability metadata for '{name}' disagrees with the shared "
                f"execution policy: metadata={sorted(capability.effects)}, "
                f"policy={sorted(policy.get(name, frozenset()))}."
            )
        node = registered[tuple(name.split())]
        option_flags = {flag for param in node.params for flag in getattr(param, "opts", [])}
        if capability.preview and "--dry-run" not in option_flags:
            raise CapabilitiesError(
                f"Command '{name}' declares preview support but has no --dry-run option."
            )
        if not capability.preview and "--dry-run" in option_flags:
            raise CapabilitiesError(
                f"Command '{name}' has a --dry-run option but does not declare preview support."
            )
        if capability.output.ndjson != ("--ndjson" in option_flags):
            raise CapabilitiesError(
                f"Command '{name}' NDJSON declaration disagrees with its registered options."
            )
        if capability.output.raw != ("--raw" in option_flags):
            raise CapabilitiesError(
                f"Command '{name}' raw declaration disagrees with its registered options."
            )
        if capability.destructive and not capability.requires_authorization:
            raise CapabilitiesError(
                f"Command '{name}' is destructive but does not require mutation authorization."
            )
        for urn in capability.output.schemas:
            _verify_schema_urns(urn)


def build_capabilities_manifest(app: Any, *, cli_version: str) -> dict[str, Any]:
    """Build the deterministic capabilities manifest from registration + metadata.

    Args:
        app: The root Typer app (or an already-built Click command tree).
        cli_version: Installed CLI version string.

    Returns:
        The manifest as a plain, JSON-serializable dictionary.

    Raises:
        CapabilitiesError: If the metadata and registered tree disagree.
    """
    validate_capabilities(app)
    root = _coerce_root_app(app)
    registered = _walk_commands(root, ())

    arguments, options = _project_command(root)

    commands = [
        _command_entry(path, COMMAND_CAPABILITIES[" ".join(path)], registered[path])
        for path in sorted(registered)
    ]

    return {
        "manifest_version": CAPABILITIES_MANIFEST_VERSION,
        "taxonomy_version": CAPABILITIES_TAXONOMY_VERSION,
        "cli": {"name": "monarch-cli", "command": "monarch", "version": cli_version},
        "taxonomy": {
            "effects": sorted(effect.value for effect in Effect),
            "safety_flags": [
                "requires_authorization",
                "requires_destructive_confirmation",
                "interactive",
                "supports_preview",
            ],
        },
        "output": _global_output_section(),
        "safety": _safety_section(),
        "schema_contracts": _schema_contract_entries(),
        "operation_contracts": _operation_contract_entries(),
        "global": {"arguments": arguments, "options": options},
        "commands": commands,
    }


def render_capabilities_manifest(app: Any, *, cli_version: str) -> str:
    """Return the canonical byte-for-byte serialization of the manifest.

    Keys are sorted and indentation is fixed so repeated runs over the same
    installation serialize identically.
    """
    manifest = build_capabilities_manifest(app, cli_version=cli_version)
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


__all__ = [
    "ACCOUNT_URN",
    "CAPABILITIES_COMMAND",
    "CAPABILITIES_MANIFEST_VERSION",
    "CAPABILITIES_TAXONOMY_VERSION",
    "COMMAND_CAPABILITIES",
    "ERROR_URN",
    "GLOBAL_FORMATS",
    "MUTATION_OUTCOME_URN",
    "TRANSACTION_DETAIL_URN",
    "TRANSACTION_URN",
    "CapabilitiesError",
    "CommandCapability",
    "OutputCapability",
    "build_capabilities_manifest",
    "render_capabilities_manifest",
    "validate_capabilities",
]
