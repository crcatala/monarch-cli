"""Recurring transaction transformers."""

from __future__ import annotations

from typing import Any


def transform_recurring(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten upcoming recurring transaction items."""
    rows = []
    for item in raw.get("recurringTransactionItems", []):
        stream = item.get("stream") or {}
        category = item.get("category") or {}
        account = item.get("account") or {}
        merchant = stream.get("merchant") or {}
        rows.append(
            {
                "id": item.get("transactionId"),
                "stream_id": stream.get("id"),
                "date": item.get("date"),
                "amount": item.get("amount"),
                "merchant": merchant.get("name"),
                "frequency": stream.get("frequency"),
                "category": category.get("name"),
                "category_id": category.get("id"),
                "account": account.get("displayName"),
                "account_id": account.get("id"),
                "is_past": item.get("isPast", False),
            }
        )
    return rows
