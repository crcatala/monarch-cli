"""Tests for holdings normalization."""

from __future__ import annotations

import pytest

from monarch_cli.core.exceptions import APIError
from monarch_cli.transformers.investments import (
    transform_account_holdings,
    transform_investment_accounts,
)

ACCOUNT = {"id": "acct-2", "name": "Brokerage"}


def test_holdings_normalizes_context_and_nulls() -> None:
    raw = {
        "portfolio": {
            "aggregateHoldings": {
                "edges": [
                    {
                        "node": {
                            "id": "node-1",
                            "quantity": None,
                            "basis": 10,
                            "totalValue": None,
                            "lastSyncedAt": None,
                            "holdings": [{"ticker": "ABC", "name": "Fallback"}],
                            "security": {
                                "id": "sec-1",
                                "ticker": "ABC",
                                "name": "Alpha",
                                "type": "stock",
                                "typeDisplay": "Stock",
                                "currentPrice": None,
                            },
                        }
                    }
                ]
            }
        }
    }
    assert transform_account_holdings(raw, ACCOUNT) == [
        {
            "account_id": "acct-2",
            "account_name": "Brokerage",
            "security_id": "sec-1",
            "holding_id": "node-1",
            "ticker": "ABC",
            "name": "Alpha",
            "security_type": "stock",
            "security_type_display": "Stock",
            "quantity": None,
            "basis": 10,
            "price": None,
            "total_value": None,
            "last_synced_at": None,
        }
    ]


def test_holdings_null_containers_are_empty_and_bad_root_is_typed() -> None:
    assert transform_account_holdings({"portfolio": None}, ACCOUNT) == []
    with pytest.raises(APIError):
        transform_account_holdings([], ACCOUNT)


def test_discovery_preserves_hidden_and_holdings_count_metadata() -> None:
    accounts = transform_investment_accounts(
        {
            "accounts": [
                {
                    "id": "acct-1",
                    "displayName": "Manual",
                    "type": {"name": "other_asset"},
                    "subtype": {"name": "investment"},
                    "isHidden": True,
                    "isManual": True,
                    "holdingsCount": 2,
                    "manualInvestmentsTrackingMethod": "holdings",
                }
            ]
        }
    )
    assert accounts == [
        {
            "id": "acct-1",
            "name": "Manual",
            "type": "other_asset",
            "subtype": "investment",
            "is_hidden": True,
            "is_manual": True,
            "holdings_count": 2,
            "manual_tracking": "holdings",
        }
    ]
