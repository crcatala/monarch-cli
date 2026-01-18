"""Account transformers - convert raw API responses to CLI-friendly format.

The transformed schema is a contract with AI agents. Field names and types
are stable - changes are breaking.
"""

from typing import Any


def transform_account(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform a single account from raw API format.

    Args:
        raw: Raw account dict from Monarch API

    Returns:
        Normalized account dict with stable field names

    Example:
        >>> raw = {"id": "123", "displayName": "Checking", "type": {"display": "Checking"}}
        >>> transform_account(raw)
        {"id": "123", "name": "Checking", "type": "Checking", ...}
    """
    return {
        "id": raw.get("id"),
        "name": raw.get("displayName"),
        "type": raw.get("type", {}).get("display"),
        "subtype": raw.get("subtype", {}).get("display"),
        "balance": raw.get("currentBalance"),
        "institution": raw.get("institution", {}).get("name"),
        "is_active": not raw.get("isHidden", False),
        "is_manual": raw.get("isManual", False),
        "last_updated": raw.get("updatedAt"),
    }


def transform_accounts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform accounts API response.

    Args:
        raw: Raw API response containing 'accounts' list

    Returns:
        List of normalized account dicts
    """
    accounts = raw.get("accounts") or []
    return [transform_account(acc) for acc in accounts]
