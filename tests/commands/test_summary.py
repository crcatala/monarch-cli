"""Tests for the high-level summary command."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from monarch_cli.commands.summary import app

runner = CliRunner()


def test_summary_combines_net_worth_and_month_to_date_cashflow() -> None:
    """Summary combines existing stable net-worth and cashflow schemas."""
    client = MagicMock()
    captured = {}

    async def async_accounts():
        return {
            "accounts": [
                {
                    "currentBalance": 1200.0,
                    "isAsset": True,
                    "includeBalanceInNetWorth": True,
                },
                {
                    "currentBalance": -200.0,
                    "isAsset": False,
                    "includeBalanceInNetWorth": True,
                },
            ]
        }

    async def async_cashflow(**kwargs):
        captured.update(kwargs)
        return {
            "summary": [
                {
                    "summary": {
                        "sumIncome": 5000.0,
                        "sumExpense": -3500.0,
                        "savings": 1500.0,
                        "savingsRate": 30.0,
                    }
                }
            ]
        }

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 18)

    client.get_accounts = async_accounts
    client.get_cashflow_summary = async_cashflow
    with (
        patch(
            "monarch_cli.commands.summary.get_authenticated_client",
            return_value=client,
        ),
        patch("monarch_cli.commands.summary.date", FixedDate),
        patch("monarch_cli.output.progress.is_interactive", return_value=False),
    ):
        result = runner.invoke(app, ["--json"])

    assert result.exit_code == 0
    assert captured == {"start_date": "2026-08-01", "end_date": "2026-08-18"}
    assert json.loads(result.stdout) == {
        "net_worth": 1000.0,
        "total_assets": 1200.0,
        "total_liabilities": 200.0,
        "account_count": 2,
        "cashflow_period": {"start": "2026-08-01", "end": "2026-08-18"},
        "cashflow": {
            "income": 5000.0,
            "expenses": 3500.0,
            "savings": 1500.0,
            "savings_rate": 30.0,
        },
    }
