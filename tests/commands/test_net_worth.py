"""Tests for the net-worth command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from monarch_cli.commands.net_worth import app

runner = CliRunner()


def test_net_worth_uses_only_included_accounts() -> None:
    """Net worth excludes opted-out accounts and reports liabilities as a magnitude."""
    client = MagicMock()

    async def async_accounts():
        return {
            "accounts": [
                {
                    "id": "asset",
                    "displayName": "Savings",
                    "currentBalance": 1000.0,
                    "isAsset": True,
                    "includeBalanceInNetWorth": True,
                },
                {
                    "id": "debt",
                    "displayName": "Card",
                    "currentBalance": -250.0,
                    "isAsset": False,
                    "includeBalanceInNetWorth": True,
                },
                {
                    "id": "excluded",
                    "displayName": "Excluded",
                    "currentBalance": 5000.0,
                    "isAsset": True,
                    "includeBalanceInNetWorth": False,
                },
            ]
        }

    client.get_accounts = async_accounts
    with (
        patch(
            "monarch_cli.commands.net_worth.get_authenticated_client",
            return_value=client,
        ),
        patch("monarch_cli.output.progress.is_interactive", return_value=False),
    ):
        result = runner.invoke(app, ["--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "net_worth": 750.0,
        "total_assets": 1000.0,
        "total_liabilities": 250.0,
        "account_count": 2,
    }
