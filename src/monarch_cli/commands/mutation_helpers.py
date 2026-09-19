"""Small shared command-layer primitives for guarded mutations (mc-46gq).

Only the primitives duplicated across the transaction tag and split commands
live here: object coercion, upstream payload-error parsing, transaction-ID
validation, and destructive confirmation. This is deliberately *not* a generic
mutation pipeline — authorization, execution, verification, and outcome
assembly stay in their existing modules.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.config import get_config
from ..core.exceptions import APIError, ValidationError
from ..core.prompting import confirm_action


def as_object(value: Any, label: str) -> Mapping[str, Any]:
    """Coerce an upstream value to a mapping or raise a malformed-response error."""
    if not isinstance(value, Mapping):
        raise APIError(
            message=f"Malformed {label} response.",
            details={"expected": "object", "received": type(value).__name__},
        )
    return value


def payload_error_details(errors: Any) -> list[dict[str, Any]]:
    """Normalize an upstream ``errors`` array into stable, sanitized details.

    Unknown shapes degrade to a generic message rather than leaking raw
    payloads. Recognized per-error keys are ``message``, ``code``, ``field``,
    and nested ``fieldErrors``.
    """
    if not isinstance(errors, list):
        return [{"message": "The service returned an invalid error payload."}]
    result: list[dict[str, Any]] = []
    for error in errors:
        if not isinstance(error, Mapping):
            result.append({"message": "The service returned an invalid error payload."})
            continue
        item: dict[str, Any] = {}
        for key in ("message", "code", "field"):
            if isinstance(error.get(key), str):
                item[key] = error[key]
        field_errors = error.get("fieldErrors")
        if isinstance(field_errors, list):
            item["field_errors"] = [
                {
                    key: entry[key]
                    for key in ("field", "messages")
                    if isinstance(entry, Mapping) and key in entry
                }
                for entry in field_errors
                if isinstance(entry, Mapping)
            ]
        result.append(item or {"message": "The service rejected the request."})
    return result


def validate_transaction_id(transaction_id: str) -> None:
    """Reject an empty (or whitespace-only) transaction target before any work."""
    if not transaction_id.strip():
        raise ValidationError("Transaction ID must not be empty.", field="transaction_id")


def reject_positional_targets(legacy: list[str] | None) -> None:
    """Reject a removed positional transaction ID with an actionable error.

    The removed positional form is never silently accepted or reinterpreted;
    callers are pointed at the replacement option instead.
    """
    if legacy:
        raise ValidationError(
            "Positional transaction IDs are no longer supported; use --transaction-id.",
            field="transaction_id",
            details={"removed_positional": True, "replacement_option": "--transaction-id"},
        )


def confirm_destructive(message: str, *, operation: str) -> None:
    """Apply the shared destructive-confirmation policy for one mutation.

    ``--yes`` (or ``confirm_destructive=false``) bypasses the prompt; a
    declined confirmation is a structured validation error.
    """
    if not get_config().confirm_destructive:
        return
    if not confirm_action(
        message,
        missing_input="destructive confirmation",
        remedy="pass --yes (after --allow-mutations) or disable confirm_destructive",
        operation=operation,
    ):
        raise ValidationError("Mutation was not confirmed.", field="confirmation")


__all__ = [
    "as_object",
    "payload_error_details",
    "validate_transaction_id",
    "reject_positional_targets",
    "confirm_destructive",
]
