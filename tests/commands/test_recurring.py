"""Tests for recurring transaction commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from monarch_cli.commands.recurring import app

runner = CliRunner()


def test_recurring_list_returns_stable_rows() -> None:
    """Recurring items are flattened without leaking upstream nesting."""
    client = MagicMock()

    async def async_recurring(**_kwargs):
        return {
            "recurringTransactionItems": [
                {
                    "transactionId": "txn_1",
                    "date": "2026-08-20",
                    "amount": -19.99,
                    "isPast": False,
                    "stream": {
                        "id": "stream_1",
                        "frequency": "monthly",
                        "merchant": {"name": "Example"},
                    },
                    "category": {"id": "cat_1", "name": "Subscriptions"},
                    "account": {"id": "acc_1", "displayName": "Checking"},
                }
            ]
        }

    client.get_recurring_transactions = async_recurring
    with (
        patch(
            "monarch_cli.commands.recurring.get_authenticated_client",
            return_value=client,
        ),
        patch("monarch_cli.output.progress.is_interactive", return_value=False),
    ):
        result = runner.invoke(
            app,
            ["--start", "2026-08-01", "--end", "2026-08-31", "--json"],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [
        {
            "id": "txn_1",
            "stream_id": "stream_1",
            "date": "2026-08-20",
            "amount": -19.99,
            "merchant": "Example",
            "frequency": "monthly",
            "category": "Subscriptions",
            "category_id": "cat_1",
            "account": "Checking",
            "account_id": "acc_1",
            "is_past": False,
        }
    ]
