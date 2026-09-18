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
- ``needs_review`` and opaque ``review_status`` are exposed independently when
  supplied by the selected upstream endpoint. ``review_status`` is nullable;
  detail responses from the released public client may omit it.
- A present-but-null nested relationship (for example ``merchant: null``)
  yields ``null`` rather than raising.
- Unknown additive upstream fields are ignored.
- ``--raw`` output bypasses these transformers entirely and preserves the
  upstream structure, including null containers and unknown fields.
"""

from __future__ import annotations

from typing import Any

from ..core.exceptions import NotFoundError
from .nesting import (
    bool_or_default,
    list_or_empty,
    mapping_or_empty,
    nested_get,
    require_object,
)


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
        "needs_review": bool_or_default(nested_get(transaction, "needsReview"), False),
        "review_status": _opaque_str(nested_get(transaction, "reviewStatus")),
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


def _opaque_str(value: Any) -> str | None:
    """Pass through an opaque upstream string, or ``None`` for any other shape."""
    return value if isinstance(value, str) else None


def _normalize_attachments(raw_attachments: Any) -> list[dict[str, Any]]:
    """Normalize the upstream ``attachments`` collection, tolerating nulls."""
    return [
        {
            "id": nested_get(attachment, "id"),
            "filename": nested_get(attachment, "filename"),
            "extension": nested_get(attachment, "extension"),
            "size_bytes": nested_get(attachment, "sizeBytes"),
        }
        for attachment in list_or_empty(raw_attachments)
    ]


def _normalize_tags(raw_tags: Any) -> list[dict[str, Any]]:
    """Normalize the upstream ``tags`` collection, tolerating nulls."""
    return [
        {
            "id": nested_get(tag, "id"),
            "name": nested_get(tag, "name"),
            "color": nested_get(tag, "color"),
        }
        for tag in list_or_empty(raw_tags)
    ]


def _normalize_splits(raw_splits: Any) -> list[dict[str, Any]]:
    """Normalize the upstream ``splitTransactions`` collection, tolerating nulls."""
    return [
        {
            "id": nested_get(split, "id"),
            "amount": nested_get(split, "amount"),
            "merchant": nested_get(split, "merchant", "name"),
            "category": nested_get(split, "category", "name"),
        }
        for split in list_or_empty(raw_splits)
    ]


def _normalize_original_transaction(raw_original: Any) -> dict[str, Any] | None:
    """Normalize the upstream ``originalTransaction`` object, tolerating nulls."""
    original = mapping_or_empty(raw_original)
    if not original:
        return None
    return {
        "id": nested_get(original, "id"),
        "date": nested_get(original, "date"),
        "amount": nested_get(original, "amount"),
        "merchant_name": nested_get(original, "merchant", "name"),
    }


def transform_transaction_detail(raw: Any, requested_id: str | None = None) -> dict[str, Any]:
    """Transform a single-transaction detail response into normalized output.

    The upstream ``get_transaction_details`` response wraps the transaction in
    a ``getTransaction`` container. An absent or present-but-null container
    means the requested transaction does not exist (or is not visible) and
    raises a typed :class:`NotFoundError`; a malformed non-object container
    raises a typed :class:`APIError`.

    Requested-versus-returned identity is always observable: ``requested_id``
    is echoed back, ``redirected`` is ``True`` when the returned transaction
    ID differs from the requested ID (the upstream service redirects a
    pending identifier to its posted replacement by default), and the
    normalized ``original_transaction`` object is included when upstream
    provides it.

    Args:
        raw: Raw API response from ``get_transaction_details``. Must be an
            object containing a ``getTransaction`` object (or null).
        requested_id: The transaction ID the caller asked for, echoed into
            ``requested_id`` for requested-versus-returned observability.

    Returns:
        Normalized transaction detail dict with stable field names. Pending
        state (``is_pending``, from the upstream ``pending`` field), review
        state (``needs_review``), and the opaque upstream ``review_status``
        are exposed as distinct concepts. ``review_status`` remains ``None``
        when the public detail response omits it.

    Raises:
        APIError: If ``raw`` is not an object, or ``getTransaction`` is
            present but not an object.
        NotFoundError: If ``getTransaction`` is absent or null.
    """
    response = require_object(raw, "transaction detail")

    detail = response.get("getTransaction")
    if detail is None:
        raise NotFoundError(
            message="Transaction not found.",
            resource_type="transaction",
            resource_id=requested_id,
        )
    require_object(detail, "transaction detail object")

    transaction_id = nested_get(detail, "id")
    return {
        "id": transaction_id,
        "requested_id": requested_id,
        "redirected": (
            requested_id is not None
            and isinstance(transaction_id, str)
            and transaction_id != requested_id
        ),
        "original_transaction": _normalize_original_transaction(
            nested_get(detail, "originalTransaction")
        ),
        "date": nested_get(detail, "date"),
        "amount": nested_get(detail, "amount"),
        "description": _description(detail),
        "category": nested_get(detail, "category", "name"),
        "category_id": nested_get(detail, "category", "id"),
        "account": nested_get(detail, "account", "displayName"),
        "account_id": nested_get(detail, "account", "id"),
        "is_pending": _is_pending(detail),
        "needs_review": bool_or_default(nested_get(detail, "needsReview"), False),
        "review_status": _opaque_str(nested_get(detail, "reviewStatus")),
        "notes": nested_get(detail, "notes"),
        "is_recurring": bool_or_default(nested_get(detail, "isRecurring"), False),
        "hidden_from_reports": bool_or_default(nested_get(detail, "hideFromReports"), False),
        "is_manual": bool_or_default(nested_get(detail, "isManual"), False),
        "attachments": _normalize_attachments(nested_get(detail, "attachments")),
        "tags": _normalize_tags(nested_get(detail, "tags")),
        "split": {
            "is_split": bool_or_default(nested_get(detail, "isSplitTransaction"), False),
            "has_split_transactions": bool_or_default(
                nested_get(detail, "hasSplitTransactions"), False
            ),
            "splits": _normalize_splits(nested_get(detail, "splitTransactions")),
        },
    }
