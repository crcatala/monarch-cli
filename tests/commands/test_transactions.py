"""Tests for transaction commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transactions import _parse_date, app

runner = CliRunner()


class TestParseDateHelper:
    """Tests for the date parsing helper."""

    def test_parse_valid_date(self) -> None:
        """Parse valid date string."""
        from datetime import date

        result = _parse_date("2024-06-15")
        assert result == date(2024, 6, 15)

    def test_parse_none_returns_none(self) -> None:
        """Parse None returns None."""
        result = _parse_date(None)
        assert result is None

    def test_parse_invalid_date_raises(self) -> None:
        """Parse invalid date raises typer.BadParameter."""
        import typer

        with pytest.raises(typer.BadParameter) as exc_info:
            _parse_date("not-a-date")
        assert "Invalid date format" in str(exc_info.value)
        assert "YYYY-MM-DD" in str(exc_info.value)


@pytest.fixture
def mock_authenticated_client() -> MagicMock:
    """Create a mock authenticated client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def sample_transactions_response() -> dict:
    """Sample transactions API response."""
    return {
        "allTransactions": {
            "results": [
                {
                    "id": "txn_123",
                    "date": "2024-01-15",
                    "amount": -45.67,
                    "merchant": {"name": "Coffee Shop"},
                    "plaidName": "COFFEE SHOP #123",
                    "category": {"id": "cat_food", "name": "Food & Drink"},
                    "account": {"id": "acc_123", "displayName": "Chase Checking"},
                    "isPending": False,
                    "notes": None,
                },
                {
                    "id": "txn_456",
                    "date": "2024-01-14",
                    "amount": -120.00,
                    "merchant": {"name": "Grocery Store"},
                    "plaidName": "GROCERY STORE",
                    "category": {"id": "cat_groceries", "name": "Groceries"},
                    "account": {"id": "acc_123", "displayName": "Chase Checking"},
                    "isPending": True,
                    "notes": "Weekly groceries",
                },
            ]
        }
    }


@pytest.fixture
def transformed_transactions() -> list[dict]:
    """Expected transformed transactions."""
    return [
        {
            "id": "txn_123",
            "date": "2024-01-15",
            "amount": -45.67,
            "description": "Coffee Shop",
            "category": "Food & Drink",
            "category_id": "cat_food",
            "account": "Chase Checking",
            "account_id": "acc_123",
            "is_pending": False,
            "notes": None,
        },
        {
            "id": "txn_456",
            "date": "2024-01-14",
            "amount": -120.00,
            "description": "Grocery Store",
            "category": "Groceries",
            "category_id": "cat_groceries",
            "account": "Chase Checking",
            "account_id": "acc_123",
            "is_pending": True,
            "notes": "Weekly groceries",
        },
    ]


class TestTransactionsList:
    """Tests for the transactions list command."""

    def test_list_returns_transformed_transactions(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List command returns transformed transactions."""

        async def async_get_transactions(**_):
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert len(output) == 2
            assert output[0]["id"] == "txn_123"
            assert output[0]["description"] == "Coffee Shop"
            assert output[1]["id"] == "txn_456"

    def test_list_with_limit_and_offset(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List respects limit and offset parameters."""
        captured_kwargs = {}

        async def async_get_transactions(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--limit", "50", "--offset", "10", "--json"])

            assert result.exit_code == 0
            assert captured_kwargs["limit"] == 50
            assert captured_kwargs["offset"] == 10

    def test_list_with_date_range(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with explicit date range passes dates to API."""
        captured_kwargs = {}

        async def async_get_transactions(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app, ["list", "--start", "2024-01-01", "--end", "2024-01-31", "--json"]
            )

            assert result.exit_code == 0
            assert captured_kwargs["start_date"] == "2024-01-01"
            assert captured_kwargs["end_date"] == "2024-01-31"

    def test_list_with_preset(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with date preset resolves to date range."""
        captured_kwargs = {}

        async def async_get_transactions(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--preset", "last-30-days", "--json"])

            assert result.exit_code == 0
            # Should have resolved to date strings
            assert captured_kwargs["start_date"] is not None
            assert captured_kwargs["end_date"] is not None

    def test_list_with_account_filter(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with account filter passes account IDs."""
        captured_kwargs = {}

        async def async_get_transactions(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "-a", "acc_123", "-a", "acc_456", "--json"])

            assert result.exit_code == 0
            assert captured_kwargs["account_ids"] == ["acc_123", "acc_456"]

    def test_list_with_search(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with search term passes search to API."""
        captured_kwargs = {}

        async def async_get_transactions(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--search", "coffee", "--json"])

            assert result.exit_code == 0
            assert captured_kwargs["search"] == "coffee"

    def test_list_raw_returns_api_response(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with --raw returns raw API response."""

        async def async_get_transactions(**_):
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--raw", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert "allTransactions" in output
            assert len(output["allTransactions"]["results"]) == 2

    def test_list_ndjson_outputs_one_per_line(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with --ndjson outputs one JSON object per line."""

        async def async_get_transactions(**_):
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--ndjson"])

            assert result.exit_code == 0
            lines = result.stdout.strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["id"] == "txn_123"
            assert json.loads(lines[1])["id"] == "txn_456"

    def test_list_table_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List with --format table outputs a table."""

        async def async_get_transactions(**_):
            return sample_transactions_response

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--format", "table"])

            assert result.exit_code == 0
            # Table output has table chars and column headers
            assert "id" in result.stdout
            assert "date" in result.stdout
            # Table contains box drawing characters
            assert "┃" in result.stdout or "|" in result.stdout

    def test_list_handles_empty_transactions(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """List handles case with no transactions."""

        async def async_get_transactions(**_):
            return {"allTransactions": {"results": []}}

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output == []

    def test_list_help_shows_examples(self) -> None:
        """List --help shows examples."""
        result = runner.invoke(app, ["list", "--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "monarch transactions list" in output
        assert "preset" in output.lower()
        assert "search" in output.lower()


class TestTransactionsUpdate:
    """Tests for the transactions update command."""

    def test_update_with_amount(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Update with --amount calls API correctly."""

        async def async_update_transaction(**_):
            return {"success": True}

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["update", "txn_123", "--amount", "25.50"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "updated"
            assert output["transaction_id"] == "txn_123"
            assert output["changes"]["amount"] == 25.50

    def test_update_with_description(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Update with --description calls API correctly."""

        async def async_update_transaction(**_):
            return {"success": True}

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["update", "txn_123", "--description", "Coffee Shop"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "updated"
            assert output["changes"]["merchant_name"] == "Coffee Shop"

    def test_update_with_category(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Update with --category calls API correctly."""

        async def async_update_transaction(**_):
            return {"success": True}

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["update", "txn_123", "--category", "cat_456"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "updated"
            assert output["changes"]["category_id"] == "cat_456"

    def test_update_with_notes(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Update with --notes calls API correctly."""

        async def async_update_transaction(**_):
            return {"success": True}

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["update", "txn_123", "--notes", "Business lunch"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "updated"
            assert output["changes"]["notes"] == "Business lunch"

    def test_update_with_multiple_changes(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Update with multiple flags applies all changes."""

        async def async_update_transaction(**_):
            return {"success": True}

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                [
                    "update",
                    "txn_123",
                    "--amount",
                    "30.00",
                    "--description",
                    "Lunch",
                    "--notes",
                    "Team lunch",
                ],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "updated"
            assert output["changes"]["amount"] == 30.00
            assert output["changes"]["merchant_name"] == "Lunch"
            assert output["changes"]["notes"] == "Team lunch"

    def test_update_dry_run(self) -> None:
        """Update with --dry-run shows changes without applying."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["update", "txn_123", "--amount", "25.50", "--dry-run"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "dry_run"
            assert output["transaction_id"] == "txn_123"
            assert output["changes"]["amount"] == 25.50
            assert "No changes applied" in output["message"]

    def test_update_no_changes_shows_error(self) -> None:
        """Update without any change flags shows error."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["update", "txn_123"])

            assert result.exit_code == 1
            output = json.loads(result.stdout)
            assert output["status"] == "error"
            assert "No changes specified" in output["message"]

    def test_update_help_shows_examples(self) -> None:
        """Update --help shows examples."""
        result = runner.invoke(app, ["update", "--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison - need to strip more codes
        import re

        output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "monarch transactions update" in output
        assert "amount" in output.lower()
        assert "dry-run" in output.lower()


class TestTransactionsApp:
    """Tests for the transactions app structure."""

    def test_no_args_shows_help(self) -> None:
        """Running transactions with no args shows help (exit code 2 is expected)."""
        result = runner.invoke(app, [])

        # no_args_is_help causes exit code 2
        assert result.exit_code == 2
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "Transaction management" in output
        assert "list" in output
        assert "update" in output

    def test_invalid_command_shows_error(self) -> None:
        """Invalid command shows error."""
        result = runner.invoke(app, ["invalid"])

        assert result.exit_code != 0
