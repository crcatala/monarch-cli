"""Centralized operation-effect taxonomy and mutation authorization policy.

Every registered CLI command declares its effects explicitly at registration
time via :func:`operation_effects`. The CLI is read-only by default: an
invocation whose parsed effect set contains ``remote_mutation`` is blocked
unless the caller passed the global ``--allow-mutations`` option in the
documented global-option position (before the command path) for this
invocation only. There is deliberately no config-file or environment-variable
path that can grant mutation authorization.

Two coordinated enforcement layers live here:

1. Registration metadata (:func:`collect_command_effects`) makes the full
   command inventory explicit and testable.
2. The shared remote-operation boundary (:func:`run_mutation_call` /
   :func:`run_read_call`) requires an explicit :class:`Operation` descriptor
   before any API call executes, refuses to run a remote mutation through
   the read path (or vice versa), and executes every remote mutation exactly
   once with a per-attempt timeout (see ``core.async_utils``).

Effect classification is always explicit metadata or an explicit parsed
invocation descriptor; it is never inferred from command names, client method
names, or GraphQL operation names.

Retry and ambiguity policy (mc-t9o7): reads keep their configured bounded
retries; remote mutations execute through the single-attempt mutation
executor and never inherit the read retry policy. Authentication is recorded
as the composite ``remote_authentication`` + ``local_credential_change``
operation (see ``auth login``) and is intentionally outside the financial
mutation executor: it refuses to run through either financial executor and
is not subject to their retry/ambiguity contract.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from .async_utils import run_api_call, run_mutation_api_call, run_mutation_api_call_async
from .exceptions import ErrorCode, MonarchCLIError
from .retry import MutationRetryPolicy


class Effect(StrEnum):
    """Operation effect taxonomy.

    A command may declare more than one effect when a single invocation
    crosses boundaries (for example ``auth login`` establishes a remote
    session and writes local credential state).
    """

    #: No local or remote state change.
    READ_ONLY = "read_only"
    #: A validated invocation that performs no state change (e.g. ``--dry-run``).
    PREVIEW = "preview"
    #: Establishes or changes a remote authentication/session relationship.
    REMOTE_AUTHENTICATION = "remote_authentication"
    #: Creates, updates, deletes, uploads, refreshes, or otherwise initiates a
    #: state-changing remote financial or service action.
    REMOTE_MUTATION = "remote_mutation"
    #: Writes or removes local authentication state.
    LOCAL_CREDENTIAL_CHANGE = "local_credential_change"


#: Attribute used to attach declared effects to a command callback. Because
#: ``handle_errors`` uses ``functools.wraps`` (which copies ``__dict__``), the
#: attribute survives decoration regardless of stack order.
EFFECTS_ATTR = "_monarch_cli_effects"


#: Retry/idempotency classification for every current remote mutation, keyed
#: by stable operation name. Every entry documents why the mutation is NOT
#: known to be safe to retry: the upstream service documents no idempotency
#: key or read-after-write verification signal, and it may have undocumented
#: audit, timestamp, notification, or job-trigger effects. Even an
#: absolute-value update must not be assumed retry-safe from final-state
#: intuition alone.
#:
#: Any future retry-enabled mutation must (1) add its entry here naming the
#: specific mechanism (``idempotency_key`` or ``read_after_write``), and
#: (2) ship operation-specific tests proving the mechanism, before its
#: executor may select a non-``NO_RETRY`` :class:`MutationRetryPolicy`.
MUTATION_RETRY_CLASSIFICATIONS: dict[str, str] = {
    "accounts refresh": (
        "no_retry: upstream documents no idempotency key or read-after-write "
        "verification for refresh requests; a timed-out request may already "
        "have started an institution sync, and retrying could trigger "
        "repeated sync work or throttling."
    ),
    "transactions update": (
        "no_retry: upstream documents no idempotency key or read-after-write "
        "verification for transaction updates; even absolute-value changes "
        "may carry undocumented audit, timestamp, or notification effects, so "
        "a timed-out update must be verified before repeating."
    ),
    "transactions batch-update": (
        "no_retry: each per-item update has the same classification as "
        "transactions update; batch execution re-runs a single-attempt "
        "executor per item and never retries an item whose outcome is "
        "unknown."
    ),
    "transactions tags create": (
        "no_retry: upstream documents no idempotency key or read-after-write "
        "verification for tag creation; a timed-out request may already have "
        "created a tag."
    ),
    "transactions tags replace": (
        "no_retry: complete-set replacement has no documented idempotency key "
        "or conditional-write mechanism."
    ),
    "transactions tags clear": (
        "no_retry: complete-set clearing has no documented idempotency key or "
        "conditional-write mechanism."
    ),
}


class MissingOperationMetadataError(Exception):
    """A registered command callback lacks explicit effect metadata."""


class PolicyViolationError(MonarchCLIError):
    """Metadata and execution policy disagree (an internal programming error)."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.POLICY_VIOLATION,
            exit_code=1,
        )


class MutationBlockedError(MonarchCLIError):
    """A remote mutation was attempted without per-invocation authorization."""

    def __init__(self, operation: Operation) -> None:
        example = f"monarch --allow-mutations {operation.command} [options]"
        message = (
            "Remote mutation blocked: this CLI is read-only unless "
            "--allow-mutations is passed for this invocation. Re-run with the "
            f"flag in the global-option position, e.g.: {example}"
        )
        super().__init__(
            message=message,
            code=ErrorCode.MUTATION_BLOCKED,
            details={
                "operation": operation.command,
                "effects": sorted(operation.effects),
                "required_flag": "--allow-mutations",
                "flag_placement": ("global options must appear before the command path"),
                "example": example,
            },
            exit_code=3,
        )


@dataclass(frozen=True)
class Operation:
    """Explicit descriptor for one parsed command invocation.

    Built from the command's declared effects, optionally reclassified for a
    validated no-effect invocation (see :func:`resolve_invocation`).
    """

    command: str
    effects: frozenset[Effect]


def operation_effects(*effects: Effect) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach explicit effect metadata to a command callback.

    Every registered command must use this decorator (directly below
    ``@handle_errors``). Tests enumerate the Typer app and fail when any
    registered command lacks metadata.
    """
    effect_set = frozenset(effects)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, EFFECTS_ATTR, effect_set)
        return func

    return decorator


def declared_effects(callback: Callable[..., Any]) -> frozenset[Effect] | None:
    """Return the effects declared on a command callback, or None."""
    effects: frozenset[Effect] | None = getattr(callback, EFFECTS_ATTR, None)
    return effects


def _effective_command_name(command_info: Any) -> str:
    """Resolve the effective CLI name of a registered Typer command.

    Mirrors Typer's own rule: an explicit name wins, otherwise the callback
    name is lowercased and underscores become dashes.
    """
    if command_info.name:
        return cast(str, command_info.name)
    return cast(str, command_info.callback.__name__).lower().replace("_", "-")


def collect_command_effects(root_app: Any) -> dict[str, frozenset[Effect]]:
    """Build the full command inventory with declared effects.

    Walks every command group registered on ``root_app`` plus any commands
    registered directly on the root app itself. Raises
    :class:`MissingOperationMetadataError` if any registered command lacks
    explicit metadata, so tests fail loudly when a new command is added
    without reviewed effect declarations.

    Returns:
        Mapping of "[group ]command" path to declared effect set.
    """
    inventory: dict[str, frozenset[Effect]] = {}
    for command_info in root_app.registered_commands:
        effects = declared_effects(command_info.callback)
        if effects is None:
            path = _effective_command_name(command_info)
            raise MissingOperationMetadataError(
                f"Registered command '{path}' is missing explicit "
                "operation-effect metadata. Declare effects with "
                "@operation_effects(...) from monarch_cli.core.operations."
            )
        inventory[_effective_command_name(command_info)] = effects

    def walk_group(group: Any, prefix: str) -> None:
        for command_info in group.registered_commands:
            name = _effective_command_name(command_info)
            path = f"{prefix} {name}".strip()
            effects = declared_effects(command_info.callback)
            if effects is None:
                raise MissingOperationMetadataError(
                    f"Registered command '{path}' is missing explicit "
                    "operation-effect metadata. Declare effects with "
                    "@operation_effects(...) from monarch_cli.core.operations."
                )
            inventory[path] = effects
        for nested in group.registered_groups:
            name = nested.name or ""
            walk_group(nested.typer_instance, f"{prefix} {name}".strip())

    for group_info in root_app.registered_groups:
        walk_group(group_info.typer_instance, group_info.name or "")
    return inventory


# --- Per-invocation authorization state -----------------------------------
#
# Deliberately process-global and set only by the root CLI callback from the
# --allow-mutations flag. It is never read from or written to config files or
# environment variables, and it never persists between invocations.

_authorized: bool = False


def set_mutation_authorized(value: bool) -> None:
    """Set mutation authorization for the current process invocation."""
    global _authorized
    _authorized = bool(value)


def mutations_authorized() -> bool:
    """Return whether the current invocation authorized remote mutations."""
    return _authorized


def reset_mutation_authorization() -> None:
    """Clear authorization (used by tests and between invocations)."""
    global _authorized
    _authorized = False


def resolve_invocation(
    command: str,
    effects: frozenset[Effect],
    *,
    dry_run: bool = False,
) -> Operation:
    """Build the parsed-operation descriptor for one invocation.

    A statically mutating command may declare a validated preview mode: when
    the no-effect option (``--dry-run``) has been confirmed on the parsed
    invocation, the policy classifies it as ``preview`` and no remote mutation
    authorization is required. Callers must still avoid any API/client calls
    on that path.
    """
    if dry_run:
        return Operation(command=command, effects=frozenset({Effect.PREVIEW}))
    return Operation(command=command, effects=frozenset(effects))


def require_mutation_authorization(operation: Operation) -> None:
    """Require ``--allow-mutations`` when the invocation mutates remote state.

    Credential and authentication effects do not imply authorization: an
    operation declaring only ``remote_authentication`` /
    ``local_credential_change`` / ``read_only`` / ``preview`` passes without
    the flag.

    Must be called before authentication lookup, API-client creation,
    destructive confirmation, or any other prompt.
    """
    if Effect.REMOTE_MUTATION not in operation.effects:
        return
    if not _authorized:
        raise MutationBlockedError(operation)


# --- Shared remote-operation boundary --------------------------------------


def run_read_call(call: Callable[[], Any], operation: Operation) -> Any:
    """Execute a read-only API call with configured bounded retries.

    The read executor refuses to run an operation whose descriptor contains
    ``remote_mutation``: a remote mutation can never silently execute through
    the read path (and thereby inherit its retry policy).
    """
    if Effect.REMOTE_MUTATION in operation.effects:
        raise PolicyViolationError(
            f"read executor refuses remote-mutation operation '{operation.command}'. "
            "Execute remote mutations through run_mutation_call()."
        )
    return run_api_call(call)


def run_mutation_call(
    call: Callable[[], Any],
    operation: Operation,
    *,
    entity_ids: tuple[str, ...] | list[str] = (),
    verification: str | None = None,
    retry_policy: MutationRetryPolicy = MutationRetryPolicy.NO_RETRY,
) -> Any:
    """Execute a remote mutation through the shared mutation boundary.

    Requires an explicit operation descriptor containing ``remote_mutation``
    and per-invocation authorization. Without either, the call is refused
    before any authentication lookup or API interaction.

    The mutation runs through the single-attempt mutation executor: no
    automatic retries (regardless of the configured ``max_retries``, which
    applies to reads only), with a per-attempt timeout from configuration.
    On an ambiguous transport failure (timeout, disconnect, or cancellation
    after invocation) it raises ``MutationAmbiguousError`` carrying the
    stable operation name, affected ``entity_ids``, and a safe verification
    instruction (exit code 4).

    Args:
        call: Zero-argument callable creating the mutation coroutine.
        operation: Descriptor containing the ``remote_mutation`` effect.
        entity_ids: Identifiers of the records the mutation targets; reported
            in ambiguity errors.
        verification: Domain-appropriate safe verification instruction; a
            generic one is generated when omitted.
        retry_policy: Mutation retry policy. Only ``NO_RETRY`` is supported;
            any other named policy is refused until its operation-specific
            mechanism and tests exist.
    """
    if Effect.REMOTE_MUTATION not in operation.effects:
        raise PolicyViolationError(
            f"Operation '{operation.command}' is not a remote mutation; "
            "execute reads through run_read_call()."
        )
    require_mutation_authorization(operation)
    return run_mutation_api_call(
        call,
        operation=operation.command,
        entity_ids=entity_ids,
        verification=verification,
        retry_policy=retry_policy,
    )


async def run_mutation_async_call(
    call: Callable[[], Awaitable[Any]],
    operation: Operation,
    *,
    entity_ids: tuple[str, ...] | list[str] = (),
    verification: str | None = None,
    retry_policy: MutationRetryPolicy = MutationRetryPolicy.NO_RETRY,
) -> Any:
    """Execute an async remote mutation at the shared policy boundary.

    Batch commands already run inside an event loop, so they use this sibling
    of :func:`run_mutation_call` rather than trying to nest the synchronous
    API runner. Authorization and effect validation happen before the async
    callable is evaluated, keeping client creation behind the boundary. The
    call is executed exactly once (no automatic retries) with a per-attempt
    timeout; ambiguous transport failures raise ``MutationAmbiguousError``.

    Args:
        call: Zero-argument callable creating the mutation coroutine.
        operation: Descriptor containing the ``remote_mutation`` effect.
        entity_ids: Identifiers of the records this call targets; reported
            in ambiguity errors.
        verification: Domain-appropriate safe verification instruction; a
            generic one is generated when omitted.
        retry_policy: Mutation retry policy. Only ``NO_RETRY`` is supported.
    """
    if Effect.REMOTE_MUTATION not in operation.effects:
        raise PolicyViolationError(
            f"Operation '{operation.command}' is not a remote mutation; "
            "execute reads through run_read_call()."
        )
    require_mutation_authorization(operation)
    return await run_mutation_api_call_async(
        call,
        operation=operation.command,
        entity_ids=entity_ids,
        verification=verification,
        retry_policy=retry_policy,
    )
