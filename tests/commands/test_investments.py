"""Tests for investment commands."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from monarch_cli.main import app

runner = CliRunner()


def _account(
    account_id: str,
    name: str,
    *,
    type_name: str = "brokerage",
    holdings_count: int = 1,
    hidden: bool = False,
) -> dict[str, Any]:
    return {
        "id": account_id,
        "displayName": name,
        "isHidden": hidden,
        "holdingsCount": holdings_count,
        "type": {"name": type_name, "display": "Investments"},
        "subtype": {"display": "Brokerage (Taxable)"},
        "institution": {"name": "Fidelity"},
    }


def _holdings_response(ticker: str, quantity: float, total_value: float) -> dict[str, Any]:
    return {
        "portfolio": {
            "aggregateHoldings": {
                "edges": [
                    {
                        "node": {
                            "id": f"holding_{ticker}",
                            "quantity": quantity,
                            "basis": total_value - 10,
                            "totalValue": total_value,
                            "lastSyncedAt": "2026-05-19",
                            "holdings": [
                                {
                                    "id": f"security_{ticker}",
                                    "name": f"{ticker} Fund",
                                    "ticker": ticker,
                                }
                            ],
                            "security": {
                                "id": f"security_{ticker}",
                                "name": f"{ticker} Fund",
                                "ticker": ticker,
                                "currentPrice": total_value / quantity,
                                "oneDayChangePercent": 1.5,
                            },
                        }
                    }
                ]
            }
        }
    }


class TestInvestmentsHoldings:
    """Tests for 'monarch investments holdings'."""

    def test_discovers_visible_investment_accounts_with_holdings(self) -> None:
        """Holdings command discovers visible brokerage accounts with holdings."""
        mock_client = MagicMock()
        mock_client.get_accounts = AsyncMock(
            return_value={
                "accounts": [
                    _account("101", "Taxable"),
                    _account("102", "Checking", type_name="depository", holdings_count=0),
                    _account("103", "Empty Brokerage", holdings_count=0),
                    _account("104", "Hidden Brokerage", hidden=True),
                ]
            }
        )
        mock_client.get_account_holdings = AsyncMock(return_value=_holdings_response("VTI", 2, 700))

        with (
            patch(
                "monarch_cli.commands.investments.get_authenticated_client",
                return_value=mock_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["investments", "holdings", "--json"])

        assert result.exit_code == 0
        rows = json.loads(result.stdout)
        assert len(rows) == 1
        assert rows[0]["account_id"] == "101"
        assert rows[0]["account_name"] == "Taxable"
        assert rows[0]["ticker"] == "VTI"
        assert rows[0]["total_value"] == 700
        mock_client.get_account_holdings.assert_awaited_once_with(101)

    def test_specific_account_ids_are_queried_even_if_hidden(self) -> None:
        """Explicit account IDs are queried even when hidden or empty in account metadata."""
        mock_client = MagicMock()
        mock_client.get_accounts = AsyncMock(
            return_value={
                "accounts": [
                    _account("104", "Hidden Brokerage", hidden=True),
                ]
            }
        )
        mock_client.get_account_holdings = AsyncMock(
            return_value=_holdings_response("VXUS", 3, 240)
        )

        with (
            patch(
                "monarch_cli.commands.investments.get_authenticated_client",
                return_value=mock_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["investments", "holdings", "--account", "104", "--json"],
            )

        assert result.exit_code == 0
        rows = json.loads(result.stdout)
        assert rows[0]["account_id"] == "104"
        assert rows[0]["account_name"] == "Hidden Brokerage"
        assert rows[0]["ticker"] == "VXUS"

    def test_aggregate_combines_holdings_by_ticker(self) -> None:
        """Aggregate mode combines holdings with the same ticker."""
        mock_client = MagicMock()
        mock_client.get_accounts = AsyncMock(
            return_value={
                "accounts": [
                    _account("101", "Taxable"),
                    _account("102", "IRA"),
                ]
            }
        )
        mock_client.get_account_holdings = AsyncMock(
            side_effect=[
                _holdings_response("VTI", 2, 700),
                _holdings_response("VTI", 3, 1050),
            ]
        )

        with (
            patch(
                "monarch_cli.commands.investments.get_authenticated_client",
                return_value=mock_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["investments", "holdings", "--aggregate", "--json"])

        assert result.exit_code == 0
        rows = json.loads(result.stdout)
        assert rows == [
            {
                "ticker": "VTI",
                "name": "VTI Fund",
                "quantity": 5,
                "basis": 1730,
                "total_value": 1750,
                "accounts": 2,
            }
        ]
