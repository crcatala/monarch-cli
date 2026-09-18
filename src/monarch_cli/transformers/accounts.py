"""Account transformers - convert raw API responses to CLI-friendly format.

The transformed schema is a contract with AI agents. Field names and types
are stable - changes are breaking.

Normalization rules (v1 contract):

- Unavailable non-boolean values (``id``, ``name``, ``type``, ``subtype``,
  ``balance``, ``institution``, ``last_updated``) normalize to ``null``;
  financial values are never invented (a missing balance is not ``0``).
- ``is_active`` and ``is_manual`` are always booleans. Absent or ``null``
  source values default to ``is_active=True`` (not hidden) and
  ``is_manual=False``.
- A present-but-null nested relationship (for example ``institution: null``)
  yields ``null`` rather than raising.
- Unknown additive upstream fields are ignored.
- ``--raw`` output bypasses these transformers entirely and preserves the
  upstream structure, including null containers and unknown fields.
"""

from __future__ import annotations

from typing import Any

from .nesting import bool_or_default, list_or_empty, nested_get, require_object


def transform_account(raw: Any) -> dict[str, Any]:
    """Transform a single account from raw API format.

    Args:
        raw: Raw account object from the Monarch API. Must be an object.

    Returns:
        Normalized account dict with stable field names.

    Raises:
        APIError: If ``raw`` is not an object.

    Example:
        >>> raw = {"id": "123", "displayName": "Checking", "type": {"display": "Checking"}}
        >>> transform_account(raw)
        {"id": "123", "name": "Checking", "type": "Checking", ...}
    """
    account = require_object(raw, "account")
    is_hidden = bool_or_default(nested_get(account, "isHidden"), False)
    return {
        "id": nested_get(account, "id"),
        "name": nested_get(account, "displayName"),
        "type": nested_get(account, "type", "display"),
        "subtype": nested_get(account, "subtype", "display"),
        "balance": nested_get(account, "currentBalance"),
        "institution": nested_get(account, "institution", "name"),
        "is_active": not is_hidden,
        "is_manual": bool_or_default(nested_get(account, "isManual"), False),
        "last_updated": nested_get(account, "updatedAt"),
    }


def transform_accounts(raw: Any) -> list[dict[str, Any]]:
    """Transform accounts API response.

    Args:
        raw: Raw API response object containing an ``accounts`` list. The
            container may be absent or ``null`` (normalizes to ``[]``).

    Returns:
        List of normalized account dicts.

    Raises:
        APIError: If ``raw`` is not an object.
    """
    response = require_object(raw, "accounts")
    return [transform_account(acc) for acc in list_or_empty(nested_get(response, "accounts"))]
