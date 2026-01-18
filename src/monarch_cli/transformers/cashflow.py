"""Cashflow data transformer for Monarch CLI."""

from __future__ import annotations

from typing import Any


def transform_cashflow_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Transform cashflow summary API response to a flat structure.

    Args:
        data: Raw cashflow summary from API with nested structure.

    Returns:
        Flattened dict with income, expenses, savings, and savings_rate.
    """
    # Navigate nested structure: data["summary"][0]["summary"]
    summary_list = data.get("summary", [])
    if not summary_list:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "savings_rate": 0.0,
        }

    inner_summary = summary_list[0].get("summary", {})

    income = inner_summary.get("sumIncome", 0.0) or 0.0
    # API returns negative expenses, convert to positive for display
    expenses = abs(inner_summary.get("sumExpense", 0.0) or 0.0)
    savings = inner_summary.get("savings", 0.0) or 0.0
    savings_rate = inner_summary.get("savingsRate", 0.0) or 0.0

    return {
        "income": income,
        "expenses": expenses,
        "savings": savings,
        "savings_rate": savings_rate,
    }
