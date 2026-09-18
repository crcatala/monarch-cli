"""Cashflow data transformer for Monarch CLI.

Normalization rules:

- The nested ``summary`` list and its inner ``summary`` block may be absent,
  ``null``, or a non-list/non-object shape; they normalize to the zero
  summary below rather than raising.
- Cashflow period aggregates keep their documented zero-for-no-data
  convention. This is the **only** in-scope numeric-default exception to the
  "financial values are never invented" rule: a missing period aggregate is
  rendered as ``0``, not ``null``, because the command reports totals for a
  period that legitimately has no activity.
- A non-object top-level payload fails with a stable typed :class:`APIError`.
"""

from __future__ import annotations

from typing import Any

from .nesting import list_or_empty, mapping_or_empty, nested_get, number_or_zero, require_object

#: Documented zero-for-no-data result for an absent or empty period summary.
_ZERO_SUMMARY: dict[str, int | float] = {
    "income": 0.0,
    "expenses": 0.0,
    "savings": 0.0,
    "savings_rate": 0.0,
}


def transform_cashflow_summary(data: Any) -> dict[str, int | float]:
    """Transform cashflow summary API response to a flat structure.

    Args:
        data: Raw cashflow summary object from the API with nested structure.

    Returns:
        Flattened dict with income, expenses, savings, and savings_rate. All
        values default to ``0.0`` when the period has no data.

    Raises:
        APIError: If ``data`` is not an object.
    """
    response = require_object(data, "cashflow summary")

    # Navigate nested structure: response["summary"][0]["summary"].
    # Absent/null containers and non-object elements degrade to the zero summary.
    summary_list = list_or_empty(nested_get(response, "summary"))
    if not summary_list:
        return dict(_ZERO_SUMMARY)

    inner_summary = mapping_or_empty(nested_get(summary_list[0], "summary"))

    income = number_or_zero(inner_summary.get("sumIncome"))
    # API returns negative expenses, convert to positive for display.
    expenses = abs(number_or_zero(inner_summary.get("sumExpense")))
    savings = number_or_zero(inner_summary.get("savings"))
    savings_rate = number_or_zero(inner_summary.get("savingsRate"))

    return {
        "income": income,
        "expenses": expenses,
        "savings": savings,
        "savings_rate": savings_rate,
    }
