"""Helpers for stable mutation command output."""

from __future__ import annotations

from typing import Any


def mutation_result(
    *,
    status: str,
    entity: str,
    id: str | None = None,
    ids: list[str] | None = None,
    result: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a consistent mutation envelope while allowing command-specific fields."""
    payload: dict[str, Any] = {
        "status": status,
        "entity": entity,
    }
    if id is not None:
        payload["id"] = id
    if ids is not None:
        payload["ids"] = ids
    payload.update(extra)
    if result is not None:
        payload["result"] = result
    return payload


def extract_id(raw: Any, *paths: tuple[str, ...]) -> str | None:
    """Extract an ID from common raw API shapes."""
    if isinstance(raw, dict) and raw.get("id"):
        return str(raw["id"])

    for path in paths:
        current = raw
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, dict) and current.get("id"):
            return str(current["id"])
        if isinstance(current, str):
            return current

    return None
