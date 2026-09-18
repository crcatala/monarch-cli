"""Tests for transaction commands."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transactions import _parse_date, app
from monarch_cli.core.exceptions import APIError
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized

runner = CliRunner()


@pytest.fixture(autouse=True)
def authorize_subcommand_tests():
    """Sub-app tests bypass the root callback's global option parser."""
    set_mutation_authorized(True)
    yield
    reset_mutation_authorization()


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
                    "pending": False,
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
                    "pending": True,
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

    def test_list_raw_preserves_null_and_unknown_fields(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        """Raw mode bypasses normalization: null containers and unknown fields survive."""
        raw_response = {
            "allTransactions": {"results": None, "totalCount": 0},
            "futureField": [1, 2, 3],
        }

        async def async_get_transactions(**_):
            return raw_response

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
            assert json.loads(result.stdout) == raw_response

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
            # The normative mutation-outcome.v1 envelope (mc-ik8o).
            assert output["schema_version"] == "mutation-outcome.v1"
            assert output["operation"] == "transactions.update"
            assert output["status"] == "succeeded"
            assert output["summary"] == {
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "ambiguous": 0,
            }
            assert output["verification"] is None
            (item,) = output["items"]
            assert item["entity"] == "transaction"
            assert item["id"] == "txn_123"
            assert item["status"] == "succeeded"
            assert item["result"] == {"changes": {"amount": 25.50}}
            assert item["error"] is None

    def test_update_transport_ambiguity_is_exit_four(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """A failed transport does not retry and reports an ambiguous outcome."""
        attempts = 0

        async def async_update_transaction(**_kwargs):
            nonlocal attempts
            attempts += 1
            raise ConnectionError("secret transport detail")

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["update", "txn_123", "--notes", "Review"])

        assert result.exit_code == 4
        assert attempts == 1
        output = json.loads(result.stdout)
        assert output["status"] == "ambiguous"
        assert output["summary"]["ambiguous"] == 1
        (item,) = output["items"]
        assert item["status"] == "ambiguous"
        assert item["result"] is None
        assert item["error"]["code"] == "MUTATION_AMBIGUOUS"
        assert item["error"]["details"]["remote_state"] == "unknown"
        # Ambiguity requires recovery guidance with a safe tokenized command.
        assert output["verification"]["required"] is True
        assert "confirm whether the update was applied" in output["verification"]["message"].lower()
        assert output["verification"]["command"] == ["monarch", "transactions", "list"]
        # No raw upstream exception text leaks into the outcome.
        assert "secret transport detail" not in result.stdout

    def test_update_definite_api_failure_is_failed_envelope_exit_one(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """A definitive application rejection is a failed outcome, exit 1."""

        async def async_update_transaction(**_kwargs):
            raise APIError("transaction not found", status_code=404)

        mock_authenticated_client.update_transaction = async_update_transaction

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["update", "txn_123", "--notes", "Review"])

        assert result.exit_code == 1
        output = json.loads(result.stdout)
        assert output["status"] == "failed"
        assert output["summary"] == {
            "total": 1,
            "succeeded": 0,
            "failed": 1,
            "ambiguous": 0,
        }
        (item,) = output["items"]
        assert item["status"] == "failed"
        assert item["result"] is None
        assert item["error"]["code"] == "API_ERROR"
        assert item["error"]["details"]["status_code"] == 404
        # No follow-up verification is needed for a definitive failure.
        assert output["verification"] is None

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
            result = runner.invoke(
                app,
                ["update", "txn_123", "--description", "Coffee Shop"],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "succeeded"
            assert output["items"][0]["result"] == {"changes": {"merchant_name": "Coffee Shop"}}

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
            result = runner.invoke(
                app,
                ["update", "txn_123", "--category", "cat_456"],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "succeeded"
            assert output["items"][0]["result"] == {"changes": {"category_id": "cat_456"}}

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
            result = runner.invoke(
                app,
                ["update", "txn_123", "--notes", "Business lunch"],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "succeeded"
            assert output["items"][0]["result"] == {"changes": {"notes": "Business lunch"}}

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
            assert output["status"] == "succeeded"
            assert output["items"][0]["result"]["changes"]["amount"] == 30.00
            assert output["items"][0]["result"]["changes"]["merchant_name"] == "Lunch"
            assert output["items"][0]["result"]["changes"]["notes"] == "Team lunch"

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

    def test_update_no_changes_uses_structured_error_contract(self) -> None:
        """A pre-execution validation failure is a structured error, not an outcome."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["update", "txn_123"])

            # Validation failures keep the structured error contract (exit 2
            # on stderr); they are never misrepresented as mutation outcomes.
            assert result.exit_code == 2
            assert "mutation-outcome.v1" not in result.stdout
            error = json.loads(result.stderr[result.stderr.index("{") :])
            assert error["code"] == "INVALID_INPUT"
            assert "No changes specified" in error["message"]

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


class TestTransactionsBatchUpdate:
    """Tests for the transactions batch-update command."""

    def test_batch_update_with_category(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch update applies category to multiple transactions."""
        update_calls: list[dict] = []

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs)
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
                    "batch-update",
                    "txn_123",
                    "txn_456",
                    "--category",
                    "cat_food",
                ],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["schema_version"] == "mutation-outcome.v1"
            assert output["operation"] == "transactions.batch-update"
            assert output["status"] == "succeeded"
            assert output["summary"] == {
                "total": 2,
                "succeeded": 2,
                "failed": 0,
                "ambiguous": 0,
            }
            assert output["verification"] is None
            assert [item["id"] for item in output["items"]] == ["txn_123", "txn_456"]
            assert [item["status"] for item in output["items"]] == ["succeeded", "succeeded"]
            assert output["items"][0]["result"] == {"changes": {"category_id": "cat_food"}}
            assert len(update_calls) == 2

    def test_batch_update_with_notes(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch update applies notes to multiple transactions."""
        update_calls: list[dict] = []

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs)
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
                ["batch-update", "txn_123", "--notes", "Q1 Expenses"],
            )
            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "succeeded"
            assert output["summary"]["succeeded"] == 1
            assert output["items"][0]["result"] == {"changes": {"notes": "Q1 Expenses"}}

    def test_batch_update_with_stdin(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch update reads IDs from stdin."""
        update_calls: list[dict] = []

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs)
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
                ["batch-update", "--stdin", "--category", "cat_123"],
                input="txn_001\ntxn_002\ntxn_003\n",
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["summary"]["succeeded"] == 3
            assert output["summary"]["total"] == 3
            assert len(update_calls) == 3

    def test_batch_update_stdin_skips_empty_lines(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch update skips empty lines from stdin."""
        update_calls: list[dict] = []

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs)
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
                ["batch-update", "--stdin", "--category", "cat_123"],
                input="txn_001\n\ntxn_002\n\n",
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["summary"]["succeeded"] == 2
            assert output["summary"]["total"] == 2
            assert len(update_calls) == 2

    def test_batch_update_dry_run(self) -> None:
        """Batch update dry-run shows preview without applying."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(
                app,
                ["batch-update", "txn_123", "txn_456", "--category", "cat_food", "--dry-run"],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "dry_run"
            assert output["transaction_count"] == 2
            assert output["transaction_ids"] == ["txn_123", "txn_456"]
            assert output["changes"]["category_id"] == "cat_food"
            assert "Would update 2 transaction(s)" in output["message"]

    def test_batch_update_labels_ambiguity_and_preserves_order(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch output retains ordered success and ambiguous item outcomes."""
        attempts: list[str] = []

        async def async_update_transaction(**kwargs):
            transaction_id = kwargs["transaction_id"]
            attempts.append(transaction_id)
            if transaction_id == "txn_456":
                raise TimeoutError("secret transport detail")
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
                    "batch-update",
                    "txn_123",
                    "txn_456",
                    "txn_789",
                    "--category",
                    "cat_food",
                ],
            )

        assert result.exit_code == 4
        output = json.loads(result.stdout)
        assert output["status"] == "partial"
        assert output["summary"] == {
            "total": 3,
            "succeeded": 2,
            "failed": 0,
            "ambiguous": 1,
        }
        # Batch items preserve normalized input order.
        assert [item["id"] for item in output["items"]] == [
            "txn_123",
            "txn_456",
            "txn_789",
        ]
        assert [item["status"] for item in output["items"]] == [
            "succeeded",
            "ambiguous",
            "succeeded",
        ]
        assert output["items"][1]["error"]["code"] == "MUTATION_AMBIGUOUS"
        # Mixed outcomes require recovery guidance before any retry.
        assert output["verification"]["required"] is True
        assert output["verification"]["command"] == ["monarch", "transactions", "list"]
        assert "secret transport detail" not in result.stdout
        assert attempts == ["txn_123", "txn_456", "txn_789"]

    def test_batch_update_handles_partial_failures(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch update continues on partial failures."""
        call_count = 0

        async def async_update_transaction(**kwargs):
            nonlocal call_count
            call_count += 1
            # Fail on second transaction
            if kwargs.get("transaction_id") == "txn_456":
                raise Exception("API error: transaction not found")
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
                    "batch-update",
                    "txn_123",
                    "txn_456",
                    "txn_789",
                    "--category",
                    "cat_food",
                ],
            )

            # A mixture of succeeded and failed items is a partial outcome:
            # nonzero exit 4, with the ordered per-item outcomes printed and
            # sanitized error objects.
            assert result.exit_code == 4
            output = json.loads(result.stdout)
            assert output["status"] == "partial"
            assert output["summary"] == {
                "total": 3,
                "succeeded": 2,
                "failed": 1,
                "ambiguous": 0,
            }
            assert [item["id"] for item in output["items"]] == [
                "txn_123",
                "txn_456",
                "txn_789",
            ]
            assert [item["status"] for item in output["items"]] == [
                "succeeded",
                "failed",
                "succeeded",
            ]
            failed = output["items"][1]
            assert failed["result"] is None
            assert failed["error"]["code"] == "UNKNOWN"
            # Raw exception text is never copied into the contract.
            assert "API error: transaction not found" not in result.stdout
            assert output["verification"] is None

    def test_batch_update_no_ids_uses_structured_error_contract(self) -> None:
        """Missing IDs is a pre-execution validation failure, not an outcome."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["batch-update", "--category", "cat_123"])

            assert result.exit_code == 2
            assert "mutation-outcome.v1" not in result.stdout
            error = json.loads(result.stderr[result.stderr.index("{") :])
            assert error["code"] == "INVALID_INPUT"
            assert "No transaction IDs provided" in error["message"]

    def test_batch_update_no_changes_uses_structured_error_contract(self) -> None:
        """Missing changes is a pre-execution validation failure, not an outcome."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["batch-update", "txn_123"])

            assert result.exit_code == 2
            assert "mutation-outcome.v1" not in result.stdout
            error = json.loads(result.stderr[result.stderr.index("{") :])
            assert error["code"] == "INVALID_INPUT"
            assert "No changes specified" in error["message"]

    def test_batch_update_both_args_and_stdin(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Batch update combines argument IDs and stdin IDs."""
        update_calls: list[dict] = []

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs)
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
                    "batch-update",
                    "txn_arg1",
                    "--stdin",
                    "--category",
                    "cat_123",
                ],
                input="txn_stdin1\ntxn_stdin2\n",
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["summary"]["succeeded"] == 3
            assert output["summary"]["total"] == 3
            assert len(update_calls) == 3

    def test_batch_update_help_shows_examples(self) -> None:
        """Batch update --help shows examples."""
        result = runner.invoke(app, ["batch-update", "--help"])

        assert result.exit_code == 0
        import re

        output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "batch-update" in output.lower()
        assert "--stdin" in output
        assert "--category" in output
        assert "--dry-run" in output


class TestTransactionsBatchUpdateInterrupt:
    """An interrupt mid-batch reports batch-level ambiguity, not silence."""

    @staticmethod
    def _interrupting_run_async(coro: Any) -> Any:
        """Simulate a KeyboardInterrupt surfacing from the async bridge."""
        coro.close()  # Cancel the pending batch coroutine like asyncio.run does.
        raise KeyboardInterrupt()

    def test_keyboard_interrupt_mid_batch_reports_all_ids(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Ctrl-C during batch execution exits 4 with every requested ID."""
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch(
                "monarch_cli.commands.transactions.run_async",
                side_effect=TestTransactionsBatchUpdateInterrupt._interrupting_run_async,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["batch-update", "txn_1", "txn_2", "--category", "cat_food"],
            )

        assert result.exit_code == 4
        output = json.loads(result.stdout)
        assert output["status"] == "ambiguous"
        assert output["operation"] == "transactions.batch-update"
        assert [item["id"] for item in output["items"]] == ["txn_1", "txn_2"]
        assert all(item["status"] == "ambiguous" for item in output["items"])
        assert all(item["error"]["details"]["reason"] == "cancelled" for item in output["items"])
        assert output["verification"]["required"] is True
        assert "verify" in output["verification"]["message"].lower()
        assert output["verification"]["command"] == ["monarch", "transactions", "list"]
