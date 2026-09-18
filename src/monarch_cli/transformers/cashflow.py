"""Cashflow response normalization for the stable CLI contract.

The released client exposes one aggregate response for ``get_cashflow``.  Its
category and category-group amounts are signed aggregate sums; merchant
expenses are normalized to positive values, matching the existing summary
semantics.  Missing period summary values use the established zero-for-no-data
rule, while unavailable detail values remain ``None``.

``--raw`` is handled by the command before these transformers are called and
therefore preserves the upstream response unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .nesting import list_or_empty, mapping_or_empty, nested_get, number_or_zero, require_object

#: Documented zero-for-no-data result for an absent or empty period summary.
_ZERO_SUMMARY: dict[str, int | float] = {
    "income": 0.0,
    "expenses": 0.0,
    "savings": 0.0,
    "savings_rate": 0.0,
}


def _number_or_none(value: Any) -> int | float | None:
    """Keep a numeric aggregate, or preserve unavailable data as ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _summary_mapping(value: Any) -> Mapping[str, Any]:
    """Return a summary mapping from either the list or object API shape."""
    if isinstance(value, Mapping):
        return value
    items = list_or_empty(value)
    return mapping_or_empty(items[0]) if items else {}


def _summary_block(data: Any, context: str) -> Mapping[str, Any]:
    """Return the first period summary block from an aggregate response."""
    response = require_object(data, context)
    summary_entry = _summary_mapping(nested_get(response, "summary"))
    return _summary_mapping(summary_entry.get("summary"))


def _normalize_summary(data: Any, context: str) -> dict[str, int | float]:
    """Normalize the shared income/expense summary block."""
    inner_summary = _summary_block(data, context)
    if not inner_summary:
        return dict(_ZERO_SUMMARY)

    income = number_or_zero(inner_summary.get("sumIncome"))
    # The API returns expenses as a negative amount; expose positive expenses.
    expenses = abs(number_or_zero(inner_summary.get("sumExpense")))
    savings = number_or_zero(inner_summary.get("savings"))
    savings_rate = number_or_zero(inner_summary.get("savingsRate"))
    return {
        "income": income,
        "expenses": expenses,
        "savings": savings,
        "savings_rate": savings_rate,
    }


def transform_cashflow_summary(data: Any) -> dict[str, int | float]:
    """Normalize the existing cashflow summary contract.

    A missing or empty period aggregate reports zero totals, as established by
    ``cashflow summary``.  This function is also used for the ``summary``
    block returned by ``cashflow detail`` so the two commands cannot drift.
    """
    return _normalize_summary(data, "cashflow summary")


def _category_record(item: Any) -> dict[str, Any]:
    """Normalize one category aggregate while preserving signed amount."""
    category = nested_get(item, "groupBy", "category")
    group = nested_get(category, "group")
    summary = _summary_mapping(nested_get(item, "summary"))
    return {
        "id": nested_get(category, "id"),
        "name": nested_get(category, "name"),
        "group_id": nested_get(group, "id"),
        "group_type": nested_get(group, "type"),
        "amount": _number_or_none(summary.get("sum")),
    }


def _category_group_record(item: Any) -> dict[str, Any]:
    """Normalize one category-group aggregate while preserving signed amount."""
    group = nested_get(item, "groupBy", "categoryGroup")
    summary = _summary_mapping(nested_get(item, "summary"))
    return {
        "id": nested_get(group, "id"),
        "name": nested_get(group, "name"),
        "type": nested_get(group, "type"),
        "amount": _number_or_none(summary.get("sum")),
    }


def _merchant_record(item: Any) -> dict[str, Any]:
    """Normalize one merchant aggregate with positive expense semantics."""
    merchant = nested_get(item, "groupBy", "merchant")
    summary = _summary_mapping(nested_get(item, "summary"))
    expense = _number_or_none(summary.get("sumExpense"))
    return {
        "id": nested_get(merchant, "id"),
        "name": nested_get(merchant, "name"),
        "logo_url": nested_get(merchant, "logoUrl"),
        "income": _number_or_none(summary.get("sumIncome")),
        "expenses": abs(expense) if expense is not None else None,
    }


def transform_cashflow_detail(data: Any) -> dict[str, Any]:
    """Normalize a complete ``get_cashflow`` response.

    Stable output keys are ``categories``, ``category_groups``, ``merchants``,
    and ``summary``.  Missing/null aggregate collections become empty lists;
    missing fields on an individual row become ``None``.  Category amounts
    remain signed because a category can represent either income or expense.

    Raises:
        APIError: If ``data`` is not an object.
    """
    response = require_object(data, "cashflow detail")
    return {
        "categories": [
            _category_record(item) for item in list_or_empty(nested_get(response, "byCategory"))
        ],
        "category_groups": [
            _category_group_record(item)
            for item in list_or_empty(nested_get(response, "byCategoryGroup"))
        ],
        "merchants": [
            _merchant_record(item) for item in list_or_empty(nested_get(response, "byMerchant"))
        ],
        # Deliberately normalize the embedded response block once; detail does
        # not issue a separate get_cashflow_summary request.
        "summary": transform_cashflow_summary(response),
    }


__all__ = ["transform_cashflow_detail", "transform_cashflow_summary"]
