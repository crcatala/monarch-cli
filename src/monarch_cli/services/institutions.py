"""Read services for credential/institution diagnostics and subscription state."""

from __future__ import annotations

from typing import Any, cast

from ..core.adapter import get_authenticated_client
from ..core.operations import Effect, Operation, run_read_call
from ..transformers.institutions import transform_institutions, transform_subscription

INSTITUTIONS_OPERATION = Operation(
    command="institutions list", effects=frozenset({Effect.READ_ONLY})
)
SUBSCRIPTION_OPERATION = Operation(
    command="subscription show", effects=frozenset({Effect.READ_ONLY})
)


def get_institutions_raw(operation: Operation = INSTITUTIONS_OPERATION) -> dict[str, Any]:
    """Fetch the upstream institution response without transformation."""
    client = get_authenticated_client()
    return cast(dict[str, Any], run_read_call(lambda: client.get_institutions(), operation))


def list_institutions(
    *, include_deleted: bool = False, operation: Operation = INSTITUTIONS_OPERATION
) -> list[dict[str, Any]]:
    """Fetch and normalize credential-centric institution records."""
    return transform_institutions(get_institutions_raw(operation), include_deleted=include_deleted)


def get_subscription_raw(operation: Operation = SUBSCRIPTION_OPERATION) -> dict[str, Any]:
    """Fetch the complete subscription response for explicit ``--raw`` mode."""
    client = get_authenticated_client()
    return cast(dict[str, Any], run_read_call(lambda: client.get_subscription_details(), operation))


def show_subscription(operation: Operation = SUBSCRIPTION_OPERATION) -> dict[str, Any]:
    """Fetch and normalize trial and premium-entitlement state."""
    return transform_subscription(get_subscription_raw(operation))


__all__ = [
    "INSTITUTIONS_OPERATION",
    "SUBSCRIPTION_OPERATION",
    "get_institutions_raw",
    "get_subscription_raw",
    "list_institutions",
    "show_subscription",
]
