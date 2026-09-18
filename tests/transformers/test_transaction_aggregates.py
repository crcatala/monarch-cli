"""Tests for transaction summary and recurring normalization."""

from __future__ import annotations

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.transaction_aggregates import (
    transform_recurring_transactions,
    transform_transaction_summary,
)


def test_summary_maps_released_all_time_fields() -> None:
    result = transform_transaction_summary(
        {
            "aggregates": {
                "summary": {
                    "avg": -12.5,
                    "count": 4,
                    "max": 100.0,
                    "maxExpense": -80.0,
                    "sum": -50.0,
                    "sumIncome": 200.0,
                    "sumExpense": -250.0,
                    "first": "2024-01-01",
                    "last": "2024-02-01",
                }
            }
        }
    )
    assert result == {
        "count": 4,
        "average": -12.5,
        "maximum": 100.0,
        "maximum_expense": -80.0,
        "net_sum": -50.0,
        "income": 200.0,
        "expenses": 250.0,
        "first": "2024-01-01",
        "last": "2024-02-01",
    }


def test_summary_missing_values_are_null_not_zero() -> None:
    assert transform_transaction_summary({"aggregates": None}) == {
        "count": None,
        "average": None,
        "maximum": None,
        "maximum_expense": None,
        "net_sum": None,
        "income": None,
        "expenses": None,
        "first": None,
        "last": None,
    }


def test_summary_rejects_non_object_root() -> None:
    with pytest.raises(APIError):
        transform_transaction_summary(None)


def test_recurring_maps_stream_and_item_fields() -> None:
    result = transform_recurring_transactions(
        {
            "recurringTransactionItems": [
                {
                    "stream": {
                        "id": "stream-1",
                        "frequency": "monthly",
                        "amount": 42.0,
                        "isApproximate": True,
                        "merchant": {"id": "merchant-1", "name": "Utility", "logoUrl": "logo"},
                    },
                    "date": "2024-03-15",
                    "isPast": False,
                    "transactionId": "txn-1",
                    "amount": 41.5,
                    "amountDiff": -0.5,
                    "category": {"id": "cat-1", "name": "Bills"},
                    "account": {"id": "acct-1", "displayName": "Checking", "logoUrl": "acct-logo"},
                }
            ]
        }
    )
    assert result == [
        {
            "stream_id": "stream-1",
            "frequency": "monthly",
            "merchant_id": "merchant-1",
            "merchant": "Utility",
            "merchant_logo_url": "logo",
            "account_id": "acct-1",
            "account": "Checking",
            "account_logo_url": "acct-logo",
            "category_id": "cat-1",
            "category": "Bills",
            "expected_date": "2024-03-15",
            "expected_amount": 42.0,
            "observed_amount": 41.5,
            "amount_diff": -0.5,
            "is_approximate": True,
            "is_past": False,
            "transaction_id": "txn-1",
        }
    ]


def test_recurring_null_and_empty_containers_are_empty() -> None:
    assert transform_recurring_transactions({"recurringTransactionItems": None}) == []
    assert transform_recurring_transactions({}) == []
