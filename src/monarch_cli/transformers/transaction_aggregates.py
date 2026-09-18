"""Normalization for transaction aggregate and recurring activity responses.

The released Monarch client exposes a filterless transaction summary and a
month-defaulted recurring activity endpoint.  These transformers keep those
upstream semantics explicit: summary data is all-time, recurring rows retain
only fields supplied by the service, and unavailable values are ``None`` (or
an empty collection for a missing collection).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .nesting import bool_or_default, list_or_empty, mapping_or_empty, nested_get, require_object


def _number_or_none(value: Any) -> int | float | None:
    """Keep a real numeric value and normalize malformed values to ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _summary_object(response: Mapping[str, Any]) -> Mapping[str, Any]:
    """Locate the released ``aggregates.summary`` object.

    The released client returns ``aggregates`` as a one-item list, while
    earlier fixtures used a direct object. Accept both shapes without merging
    or calculating values locally.
    """
    aggregates = response.get("aggregates")
    if isinstance(aggregates, Mapping):
        summary = aggregates.get("summary")
    elif isinstance(aggregates, list):
        summary = nested_get(aggregates[0], "summary") if aggregates else None
    else:
        summary = None
    if summary is None:
        summary = nested_get(response, "summary")
    return mapping_or_empty(summary)


def transform_transaction_summary(data: Any) -> dict[str, Any]:
    """Normalize the filterless, all-time transaction summary.

    ``sum`` is the signed net sum returned by the API. ``sumExpense`` is
    negative for expenses upstream and is exposed as a positive ``expenses``
    value, matching the existing cashflow summary contract. No zero values are
    invented when the upstream aggregate or one of its fields is unavailable.
    """
    response = require_object(data, "transaction summary")
    summary = _summary_object(response)
    sum_expense = _number_or_none(summary.get("sumExpense"))
    return {
        "count": summary.get("count")
        if isinstance(summary.get("count"), int) and not isinstance(summary.get("count"), bool)
        else None,
        "average": _number_or_none(summary.get("avg")),
        "maximum": _number_or_none(summary.get("max")),
        "maximum_expense": _number_or_none(summary.get("maxExpense")),
        "net_sum": _number_or_none(summary.get("sum")),
        "income": _number_or_none(summary.get("sumIncome")),
        "expenses": abs(sum_expense) if sum_expense is not None else None,
        "first": summary.get("first"),
        "last": summary.get("last"),
    }


def _recurring_item(item: Any) -> dict[str, Any]:
    """Normalize one upcoming recurring item without deriving values."""
    stream = nested_get(item, "stream")
    merchant = nested_get(item, "stream", "merchant")
    account = nested_get(item, "account")
    category = nested_get(item, "category")
    return {
        "stream_id": nested_get(stream, "id"),
        "frequency": nested_get(stream, "frequency"),
        "merchant_id": nested_get(merchant, "id"),
        "merchant": nested_get(merchant, "name"),
        "merchant_logo_url": nested_get(merchant, "logoUrl"),
        "account_id": nested_get(account, "id"),
        "account": nested_get(account, "displayName"),
        "account_logo_url": nested_get(account, "logoUrl"),
        "category_id": nested_get(category, "id"),
        "category": nested_get(category, "name"),
        "expected_date": nested_get(item, "date"),
        "expected_amount": _number_or_none(nested_get(stream, "amount")),
        "observed_amount": _number_or_none(nested_get(item, "amount")),
        "amount_diff": _number_or_none(nested_get(item, "amountDiff")),
        "is_approximate": bool_or_default(nested_get(stream, "isApproximate"), False),
        "is_past": bool_or_default(nested_get(item, "isPast"), False),
        "transaction_id": nested_get(item, "transactionId"),
    }


def transform_recurring_transactions(data: Any) -> list[dict[str, Any]]:
    """Normalize the released recurring activity collection."""
    response = require_object(data, "recurring transactions")
    return [
        _recurring_item(item) for item in list_or_empty(response.get("recurringTransactionItems"))
    ]


__all__ = ["transform_recurring_transactions", "transform_transaction_summary"]
