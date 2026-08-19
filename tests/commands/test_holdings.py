"""Tests for investment holdings commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from monarch_cli.commands.holdings import app

runner = CliRunner()


def test_holdings_filters_positions_and_aggregates_by_security() -> None:
    """Ticker filters preserve per-account legs and aggregate their concentration."""
    client = MagicMock()

    async def async_accounts():
        return {
            "accounts": [
                {
                    "id": "brokerage_1",
                    "displayName": "Taxable",
                    "currentBalance": 1000.0,
                    "isAsset": True,
                    "includeBalanceInNetWorth": True,
                    "type": {"name": "brokerage"},
                },
                {
                    "id": "brokerage_2",
                    "displayName": "Retirement",
                    "currentBalance": 3000.0,
                    "isAsset": True,
                    "includeBalanceInNetWorth": True,
                    "type": {"name": "brokerage"},
                },
            ]
        }

    async def async_holdings(account_id):
        values = {
            "brokerage_1": [
                {
                    "quantity": 2,
                    "basis": 100.0,
                    "totalValue": 200.0,
                    "security": {
                        "ticker": "MSFT",
                        "name": "Microsoft",
                        "currentPrice": 100.0,
                    },
                },
                {
                    "quantity": 1,
                    "basis": 50.0,
                    "totalValue": 50.0,
                    "security": {"ticker": "SMALL", "name": "Small Co"},
                },
            ],
            "brokerage_2": [
                {
                    "quantity": 3,
                    "basis": 240.0,
                    "totalValue": 300.0,
                    "security": {
                        "ticker": "MSFT",
                        "name": "Microsoft",
                        "currentPrice": 100.0,
                    },
                }
            ],
        }
        return {
            "portfolio": {
                "aggregateHoldings": {"edges": [{"node": node} for node in values[account_id]]}
            }
        }

    client.get_accounts = async_accounts
    client.get_account_holdings = async_holdings
    with (
        patch(
            "monarch_cli.commands.holdings.get_authenticated_client",
            return_value=client,
        ),
        patch("monarch_cli.output.progress.is_interactive", return_value=False),
    ):
        result = runner.invoke(
            app,
            ["--ticker", "msft", "--min-value", "100", "--json"],
        )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["net_worth"] == 4000.0
    assert data["filtered"] is True
    assert data["totals"] == {
        "value": 500.0,
        "basis": 340.0,
        "gain": 160.0,
        "pct_of_net_worth": 0.125,
    }
    assert data["by_security"] == [
        {
            "ticker": "MSFT",
            "name": "Microsoft",
            "quantity": 5.0,
            "value": 500.0,
            "basis": 340.0,
            "gain": 160.0,
            "pct_of_net_worth": 0.125,
            "accounts": ["Taxable", "Retirement"],
        }
    ]
    assert [position["account"] for position in data["positions"]] == [
        "Retirement",
        "Taxable",
    ]
