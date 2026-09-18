"""Null-safe traversal helpers for the transformer normalization boundary.

External financial APIs may return present-but-null nested objects, omit
optional collections, or evolve their response shape over time. This module
is the single reusable place where the transformers tolerate those shapes.
Command handlers and services must not grow ad hoc defensive traversal; they
consume already-normalized domain values from the transformer functions.

The helpers deliberately do not invent values: a missing or non-mapping
intermediate node yields ``None`` (or an empty container) rather than raising
or fabricating financial data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.exceptions import APIError


def require_object(value: Any, context: str) -> Mapping[str, Any]:
    """Validate that a top-level payload is an object.

    A malformed (non-object) root is an upstream contract violation and fails
    deliberately with a stable typed :class:`APIError` rather than surfacing
    an incidental ``AttributeError`` or ``TypeError`` downstream.

    Args:
        value: The value to validate.
        context: Human-readable description of the payload, used in the error.

    Returns:
        The same value, narrowed to a mapping.

    Raises:
        APIError: If ``value`` is not a mapping.
    """
    if not isinstance(value, Mapping):
        raise APIError(
            message=f"Malformed {context} response: expected a JSON object.",
            details={"expected": "object", "received": type(value).__name__},
        )
    return value


def nested_get(source: Any, *path: str) -> Any:
    """Traverse nested mappings, returning ``None`` if any level is unusable.

    Unlike ``source.get("a", {}).get("b")``, this does not crash when an
    intermediate key is present but ``null``; a non-mapping node ends the
    traversal and returns ``None``.

    Args:
        source: The value to traverse.
        *path: Ordered mapping keys to follow.

    Returns:
        The value at the path, or ``None`` if the path cannot be followed.
    """
    current: Any = source
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def mapping_or_empty(value: Any) -> Mapping[str, Any]:
    """Return ``value`` when it is a mapping, otherwise an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def list_or_empty(value: Any) -> list[Any]:
    """Return a shallow copy of ``value`` when it is a list, otherwise ``[]``.

    Absent and present-but-null collection containers therefore normalize to
    empty lists.
    """
    return list(value) if isinstance(value, list) else []


def bool_or_default(value: Any, default: bool) -> bool:
    """Normalize an upstream boolean field to a real ``bool``.

    Only genuine booleans are accepted. Absent, ``null``, or drifted
    non-``bool`` values (for example a stringified ``"false"``) use
    ``default`` rather than being coerced, so a malformed upstream shape can
    never silently flip a documented boolean default.
    """
    if isinstance(value, bool):
        return value
    return default


def number_or_zero(value: Any) -> int | float:
    """Return a numeric value unchanged, or ``0`` for unavailable/malformed data.

    This backs the cashflow aggregates' documented zero-for-no-data
    convention: the only in-scope numeric-default exception in the normalized
    contract. ``bool`` is explicitly rejected so ``True`` never leaks in as a
    monetary amount.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value


__all__ = [
    "bool_or_default",
    "list_or_empty",
    "mapping_or_empty",
    "nested_get",
    "number_or_zero",
    "require_object",
]
