"""Shared mutation outcome contract (``mutation-outcome.v1``).

One stable, machine-readable envelope for the result of every current
single-step and multi-step remote mutation after remote execution has been
attempted (mc-ik8o). Domain commands must not invent incompatible response
shapes: they build items with the helpers here and emit the envelope that
:func:`build_mutation_outcome` returns.

Top-level statuses:

- ``succeeded``: every requested effect is known to have succeeded.
- ``failed``: no requested effect succeeded and all failures are known to be
  definitive.
- ``ambiguous``: no effect is known to have succeeded, but at least one
  request may have changed remote state.
- ``partial``: item outcomes contain a mixture of succeeded, failed, and/or
  ambiguous states.

Per-item statuses are ``succeeded``, ``failed``, or ``ambiguous``.

Contract rules enforced here:

- ``schema_version``, ``operation``, ``status``, ``summary``, ``items``, and
  ``verification`` are always present.
- ``operation`` is a stable namespaced identifier supplied by the registry in
  this module (keyed by the shared operation descriptor's command name), never
  inferred from an upstream method or GraphQL operation name.
- Every item always contains ``entity``, ``id``, ``status``, ``result``, and
  ``error``.
- ``result`` is a normalized JSON object on success and ``null`` otherwise.
  ``error`` is ``null`` on success and otherwise contains stable ``code``,
  ``message``, and object-valued ``details``. ``result`` and ``error`` are
  never both non-null.
- ``summary.total`` equals ``len(items)`` and each status count exactly
  matches ``items``.
- ``verification`` is ``null`` when no item is ambiguous. Otherwise it
  contains ``required: true``, an actionable ``message``, and a tokenized
  ``command`` array when the CLI can provide a safe verification command.
- Additional fields are additive. Removing or changing required fields,
  status values, or their semantics requires a new schema version.

Pre-execution authorization and input-validation failures do NOT use this
contract; they keep the structured error contract (``MonarchCLIError`` via
``handle_errors``). Error objects produced here are sanitized: they never
contain credentials, raw request bodies, or arbitrary upstream exception
text. Nothing in this module claims rollback or transactionality that the
upstream API does not provide.
"""

from __future__ import annotations

from typing import Any

from .exceptions import MonarchCLIError
from .operations import PolicyViolationError

#: Version stamp carried by every envelope produced by this module.
SCHEMA_VERSION = "mutation-outcome.v1"

#: Top-level outcome statuses.
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_PARTIAL = "partial"

#: Per-item outcome statuses.
ITEM_SUCCEEDED = "succeeded"
ITEM_FAILED = "failed"
ITEM_AMBIGUOUS = "ambiguous"

#: Exit codes by top-level status. All-succeeded outcomes exit 0; definitive
#: failures use the normal operation/API nonzero error exit (1); partial and
#: ambiguous outcomes exit 4 so automation never treats an unverified write
#: as a clean success.
_EXIT_CODES: dict[str, int] = {
    STATUS_SUCCEEDED: 0,
    STATUS_FAILED: 1,
    STATUS_AMBIGUOUS: 4,
    STATUS_PARTIAL: 4,
}

#: Stable namespaced operation identifiers for the outcome envelope, keyed by
#: the shared operation descriptor's command name. A new remote mutation must
#: register its outcome operation here; the envelope never infers the name
#: from an upstream method or GraphQL operation name.
OUTCOME_OPERATIONS: dict[str, str] = {
    "accounts refresh": "accounts.refresh",
    "transactions update": "transactions.update",
    "transactions batch-update": "transactions.batch-update",
    "transactions tags create": "transactions.tags.create",
    "transactions tags replace": "transactions.tags.replace",
    "transactions tags clear": "transactions.tags.clear",
    # Test-only disposable-fixture operations (mc-584r). These are real remote
    # effects used exclusively by the gated live mutation adapter; they are
    # deliberately NOT registered as public CLI commands and must never be
    # exposed through a Typer command.
    "live-fixture account create": "live-fixture.account.create",
    "live-fixture transaction create": "live-fixture.transaction.create",
    "live-fixture transaction delete": "live-fixture.transaction.delete",
    "live-fixture account delete": "live-fixture.account.delete",
}


def outcome_operation(command: str) -> str:
    """Return the stable namespaced operation identifier for a command.

    Args:
        command: The shared operation descriptor's command name
            (e.g. ``transactions update``).

    Returns:
        The stable ``mutation-outcome.v1`` ``operation`` value.

    Raises:
        PolicyViolationError: If the command has no registered outcome
            operation name (a new mutation must be registered explicitly).
    """
    try:
        return OUTCOME_OPERATIONS[command]
    except KeyError:
        raise PolicyViolationError(
            f"Mutation command '{command}' has no registered mutation-outcome "
            "operation name. Add it to OUTCOME_OPERATIONS in "
            "core.mutation_outcomes so the envelope's operation identifier "
            "is explicit and stable."
        ) from None


def error_from_exception(exc: BaseException) -> dict[str, Any]:
    """Build a sanitized contract error object from an exception.

    Structured CLI errors contribute their stable code, message, and details
    directly. Any other exception contributes a stable generic code and
    message with only the exception class name in ``details``; raw exception
    text, request bodies, and credentials never reach the contract.

    Args:
        exc: The exception to sanitize.

    Returns:
        Error object with stable ``code``, ``message``, and object-valued
        ``details``.
    """
    if isinstance(exc, MonarchCLIError):
        return {
            "code": exc.code.value,
            "message": exc.message,
            "details": dict(exc.details),
        }
    return {
        "code": "UNKNOWN",
        "message": "The mutation failed before its outcome could be confirmed.",
        "details": {"exception_class": type(exc).__name__},
    }


def succeeded_item(entity: str, item_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a contract item for an effect known to have succeeded.

    Args:
        entity: Stable effect-specific entity name (e.g. ``transaction``).
        item_id: Best available remote identity for the effect.
        result: Normalized JSON object describing the succeeded effect.

    Returns:
        Contract item dict.
    """
    return {
        "entity": entity,
        "id": item_id,
        "status": ITEM_SUCCEEDED,
        "result": result,
        "error": None,
    }


def failed_item(
    entity: str,
    item_id: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a contract item for a definitive failure.

    Args:
        entity: Stable effect-specific entity name.
        item_id: Best available remote identity for the effect.
        code: Stable machine-readable error code.
        message: Sanitized, actionable failure message.
        details: Optional object-valued structured details.

    Returns:
        Contract item dict.
    """
    return {
        "entity": entity,
        "id": item_id,
        "status": ITEM_FAILED,
        "result": None,
        "error": {
            "code": code,
            "message": message,
            "details": dict(details) if details else {},
        },
    }


def ambiguous_item(
    entity: str,
    item_id: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a contract item for an effect whose outcome is unknown.

    The request may have been dispatched, so remote state may have changed;
    the caller must verify before retrying.

    Args:
        entity: Stable effect-specific entity name.
        item_id: Best available remote identity for the effect.
        message: Sanitized, actionable ambiguity message.
        details: Optional object-valued structured details.

    Returns:
        Contract item dict with stable ``MUTATION_AMBIGUOUS`` error code.
    """
    return {
        "entity": entity,
        "id": item_id,
        "status": ITEM_AMBIGUOUS,
        "result": None,
        "error": {
            "code": "MUTATION_AMBIGUOUS",
            "message": message,
            "details": dict(details) if details else {},
        },
    }


def verification_object(
    message: str,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Build the follow-up verification object for ambiguous outcomes.

    Args:
        message: Actionable guidance for confirming remote state safely.
        command: Tokenized safe read-only verification command when the CLI
            can provide one; ``None`` otherwise.

    Returns:
        Verification object with ``required: true``.
    """
    return {
        "required": True,
        "message": message,
        "command": list(command) if command is not None else None,
    }


def aggregate_status(items: list[dict[str, Any]]) -> str:
    """Deterministically aggregate item statuses to the top-level status.

    - All items succeeded (or there are none) -> ``succeeded``.
    - No item succeeded and at least one is ambiguous -> ``ambiguous``
      (including a mixture of failed and ambiguous items: nothing is known
      to have succeeded and remote state may have changed).
    - No item succeeded and all failures are definitive -> ``failed``.
    - Any success mixed with failed/ambiguous items -> ``partial``.

    Args:
        items: Contract item dicts in remote-effect order.

    Returns:
        One of the four top-level status values.
    """
    statuses = {item["status"] for item in items}
    if not statuses or statuses == {ITEM_SUCCEEDED}:
        return STATUS_SUCCEEDED
    if ITEM_SUCCEEDED in statuses:
        return STATUS_PARTIAL
    if ITEM_AMBIGUOUS in statuses:
        return STATUS_AMBIGUOUS
    return STATUS_FAILED


def outcome_exit_code(status: str) -> int:
    """Return the process exit code for a top-level outcome status.

    Args:
        status: One of the four top-level status values.

    Returns:
        0 for ``succeeded``, 1 for ``failed``, 4 for ``ambiguous`` and
        ``partial``.
    """
    try:
        return _EXIT_CODES[status]
    except KeyError as e:
        raise PolicyViolationError(f"Unknown mutation outcome status '{status}'.") from e


def _validate_items(items: list[dict[str, Any]]) -> None:
    """Enforce per-item contract invariants (internal programming errors)."""
    for item in items:
        missing = {"entity", "id", "status", "result", "error"} - set(item)
        if missing:
            raise PolicyViolationError(
                f"Mutation outcome item is missing required fields: {sorted(missing)}."
            )
        if item["status"] not in {ITEM_SUCCEEDED, ITEM_FAILED, ITEM_AMBIGUOUS}:
            raise PolicyViolationError(f"Invalid mutation outcome item status: {item['status']!r}.")
        if (item["result"] is None) == (item["error"] is None):
            raise PolicyViolationError(
                "Mutation outcome item must have exactly one non-null of 'result' and 'error'."
            )
        if item["error"] is not None:
            error = item["error"]
            if not isinstance(error.get("details"), dict):
                raise PolicyViolationError("Mutation outcome error 'details' must be an object.")
            if item["status"] != ITEM_AMBIGUOUS and error.get("code") == "MUTATION_AMBIGUOUS":
                raise PolicyViolationError(
                    "MUTATION_AMBIGUOUS error code is reserved for ambiguous items."
                )


def build_mutation_outcome(
    command: str,
    items: list[dict[str, Any]],
    *,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the normative ``mutation-outcome.v1`` envelope.

    Args:
        command: The shared operation descriptor's command name; mapped to
            the stable namespaced envelope ``operation`` via
            :data:`OUTCOME_OPERATIONS`.
        items: Contract items in the order effects were attempted/observed
            (input order for batches; remote-effect order for multi-stage
            workflows).
        verification: Verification object to use when any item is ambiguous.
            Ignored (envelope ``verification`` is ``null``) when no item is
            ambiguous, because no follow-up is needed.

    Returns:
        The complete envelope dict.

    Raises:
        PolicyViolationError: If the command has no registered outcome
            operation name or an item violates the contract invariants.
    """
    _validate_items(items)

    has_ambiguous = any(item["status"] == ITEM_AMBIGUOUS for item in items)
    counts = {
        ITEM_SUCCEEDED: 0,
        ITEM_FAILED: 0,
        ITEM_AMBIGUOUS: 0,
    }
    for item in items:
        counts[item["status"]] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "operation": outcome_operation(command),
        "status": aggregate_status(items),
        "summary": {
            "total": len(items),
            "succeeded": counts[ITEM_SUCCEEDED],
            "failed": counts[ITEM_FAILED],
            "ambiguous": counts[ITEM_AMBIGUOUS],
        },
        "items": items,
        "verification": verification if has_ambiguous else None,
    }


__all__ = [
    "SCHEMA_VERSION",
    "STATUS_SUCCEEDED",
    "STATUS_FAILED",
    "STATUS_AMBIGUOUS",
    "STATUS_PARTIAL",
    "ITEM_SUCCEEDED",
    "ITEM_FAILED",
    "ITEM_AMBIGUOUS",
    "OUTCOME_OPERATIONS",
    "outcome_operation",
    "error_from_exception",
    "succeeded_item",
    "failed_item",
    "ambiguous_item",
    "verification_object",
    "aggregate_status",
    "outcome_exit_code",
    "build_mutation_outcome",
]
