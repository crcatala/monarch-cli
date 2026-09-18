"""Transaction transformers - convert raw API responses to CLI-friendly format.

The transformed schema is a contract with AI agents. Field names and types
are stable - changes are breaking.

Normalization rules (v1 contract):

- Unavailable non-boolean values (``id``, ``date``, ``amount``,
  ``description``, ``category``, ``category_id``, ``account``,
  ``account_id``, ``notes``) normalize to ``null``; amounts are never
  invented (a missing amount is not ``0``).
- ``description`` falls back deterministically: non-empty ``merchant.name``,
  then ``plaidName``, then ``null``.
- ``is_pending`` is always a boolean. It reads the real upstream ``pending``
  field. Absent or ``null`` values default to ``False``.
- A present-but-null nested relationship (for example ``merchant: null``)
  yields ``null`` rather than raising.
- Unknown additive upstream fields are ignored.
- ``--raw`` output bypasses these transformers entirely and preserves the
  upstream structure, including null containers and unknown fields.
"""

from __future__ import annotations

from typing import Any

from .nesting import bool_or_default, list_or_empty, nested_get, require_object


def _description(raw: Any) -> str | None:
    """Resolve the deterministic description fallback.

    Precedence: non-empty ``merchant.name``, then ``plaidName``, then ``None``.
    """
    merchant_name = nested_get(raw, "merchant", "name")
    if isinstance(merchant_name, str) and merchant_name:
        return merchant_name
    plaid_name = nested_get(raw, "plaidName")
    if isinstance(plaid_name, str):
        return plaid_name
    return None


def _is_pending(raw: Any) -> bool:
    """Normalize pending state from the real upstream ``pending`` field."""
    return bool_or_default(nested_get(raw, "pending"), False)


def transform_transaction(raw: Any) -> dict[str, Any]:
    """Transform a single transaction from raw API format.

    Args:
        raw: Raw transaction object from the Monarch API. Must be an object.

    Returns:
        Normalized transaction dict with stable field names.

    Raises:
        APIError: If ``raw`` is not an object.

    Example:
        >>> raw = {"id": "123", "date": "2024-01-15", "merchant": {"name": "Coffee Shop"}}
        >>> transform_transaction(raw)
        {"id": "123", "date": "2024-01-15", "description": "Coffee Shop", ...}
    """
    transaction = require_object(raw, "transaction")
    return {
        "id": nested_get(transaction, "id"),
        "date": nested_get(transaction, "date"),
        "amount": nested_get(transaction, "amount"),
        "description": _description(transaction),
        "category": nested_get(transaction, "category", "name"),
        "category_id": nested_get(transaction, "category", "id"),
        "account": nested_get(transaction, "account", "displayName"),
        "account_id": nested_get(transaction, "account", "id"),
        "is_pending": _is_pending(transaction),
        "notes": nested_get(transaction, "notes"),
    }


def transform_transactions(raw: Any) -> list[dict[str, Any]]:
    """Transform transactions API response.

    Args:
        raw: Raw API response object containing an
            ``allTransactions.results`` list. The containers may be absent or
            ``null`` (normalizes to ``[]``).

    Returns:
        List of normalized transaction dicts.

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "transactions")
    results = list_or_empty(nested_get(response, "allTransactions", "results"))
    return [transform_transaction(txn) for txn in results]
