"""Transaction transformers - convert raw API responses to CLI-friendly format.

The transformed schema is a contract with AI agents. Field names and types
are stable - changes are breaking.
"""

from typing import Any


def transform_transaction(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform a single transaction from raw API format.

    Args:
        raw: Raw transaction dict from Monarch API

    Returns:
        Normalized transaction dict with stable field names

    Example:
        >>> raw = {"id": "123", "date": "2024-01-15", "merchant": {"name": "Coffee Shop"}}
        >>> transform_transaction(raw)
        {"id": "123", "date": "2024-01-15", "description": "Coffee Shop", ...}
    """
    # Description prefers merchant.name, falls back to plaidName
    merchant = raw.get("merchant") or {}
    category = raw.get("category") or {}
    account = raw.get("account") or {}

    merchant_name = merchant.get("name")
    description = (
        merchant_name if merchant_name else raw.get("merchantName") or raw.get("plaidName")
    )

    return {
        "id": raw.get("id"),
        "date": raw.get("date"),
        "amount": raw.get("amount"),
        "description": description,
        "category": category.get("name"),
        "category_id": category.get("id"),
        "account": account.get("displayName"),
        "account_id": account.get("id"),
        "is_pending": raw.get("isPending", raw.get("pending", False)),
        "notes": raw.get("notes"),
    }


def transform_transactions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform transactions API response.

    Args:
        raw: Raw API response containing 'allTransactions.results' list

    Returns:
        List of normalized transaction dicts
    """
    all_transactions = raw.get("allTransactions") or {}
    results = all_transactions.get("results") or []
    return [transform_transaction(txn) for txn in results]
