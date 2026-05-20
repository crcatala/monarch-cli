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

    def test_list_with_api_filters(
        self,
        mock_authenticated_client: MagicMock,
        sample_transactions_response: dict,
    ) -> None:
        """List exposes full upstream transaction filters."""
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
                app,
                [
                    "list",
                    "--category",
                    "cat_tax",
                    "--tag",
                    "tag_tax",
                    "--has-attachments",
                    "--has-notes",
                    "--hidden-from-reports",
                    "--is-split",
                    "--is-recurring",
                    "--imported-from-mint",
                    "--synced-from-institution",
                    "--needs-review",
                    "--visibility",
                    "all_transactions",
                    "--json",
                ],
            )

            assert result.exit_code == 0
            assert captured_kwargs["category_ids"] == ["cat_tax"]
            assert captured_kwargs["tag_ids"] == ["tag_tax"]
            assert captured_kwargs["has_attachments"] is True
            assert captured_kwargs["has_notes"] is True
            assert captured_kwargs["hidden_from_reports"] is True
            assert captured_kwargs["is_split"] is True
            assert captured_kwargs["is_recurring"] is True
            assert captured_kwargs["imported_from_mint"] is True
            assert captured_kwargs["synced_from_institution"] is True
            assert captured_kwargs["needs_review"] is True
            assert captured_kwargs["transaction_visibility"] == "all_transactions"

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

    def test_update_with_goal_visibility_and_review_flags(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Update exposes goal, report visibility, and review flags."""
        captured_kwargs: dict = {}

        async def async_update_transaction(**kwargs):
            captured_kwargs.update(kwargs)
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
                    "--goal",
                    "goal_1",
                    "--hide-from-reports",
                    "--needs-review",
                ],
            )

            assert result.exit_code == 0
            assert captured_kwargs["goal_id"] == "goal_1"
            assert captured_kwargs["hide_from_reports"] is True
            assert captured_kwargs["needs_review"] is True

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


class TestTransactionsApiCoverage:
    """Tests for API-backed transaction workflows."""

    def test_create_manual_transaction(self, mock_authenticated_client: MagicMock) -> None:
        """Create command maps required fields to API."""
        captured: dict = {}

        async def async_create(**kwargs):
            captured.update(kwargs)
            return {"id": "txn_new"}

        mock_authenticated_client.create_transaction = async_create

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
                    "create",
                    "--date",
                    "2024-01-15",
                    "--account",
                    "acc_123",
                    "--amount",
                    "-12.34",
                    "--merchant",
                    "Coffee",
                    "--category",
                    "cat_123",
                    "--notes",
                    "latte",
                    "--update-balance",
                    "--json",
                ],
            )

            assert result.exit_code == 0
            assert captured["date"] == "2024-01-15"
            assert captured["account_id"] == "acc_123"
            assert captured["amount"] == -12.34
            assert captured["merchant_name"] == "Coffee"
            assert captured["category_id"] == "cat_123"
            assert captured["notes"] == "latte"
            assert captured["update_balance"] is True

    def test_show_calls_transaction_details(self, mock_authenticated_client: MagicMock) -> None:
        """Show command calls get_transaction_details."""

        async def async_details(transaction_id: str, redirect_posted: bool = True):
            return {"id": transaction_id, "redirect": redirect_posted}

        mock_authenticated_client.get_transaction_details = async_details

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["show", "txn_123", "--no-redirect-posted", "--json"])

            assert result.exit_code == 0
            assert json.loads(result.stdout) == {"id": "txn_123", "redirect": False}

    def test_delete_requires_yes(self) -> None:
        """Transaction delete is guarded."""
        result = runner.invoke(app, ["delete", "txn_123"])

        assert result.exit_code == 1
        assert "requires --yes" in result.stdout

    def test_duplicates_calls_api(self, mock_authenticated_client: MagicMock) -> None:
        """Duplicate finder passes filters to API."""
        captured: dict = {}

        async def async_duplicates(**kwargs):
            captured.update(kwargs)
            return []

        mock_authenticated_client.find_duplicate_transactions = async_duplicates

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["duplicates", "--start", "2024-01-01", "--account", "acc_123", "--json"],
            )

            assert result.exit_code == 0
            assert captured["start_date"] == "2024-01-01"
            assert captured["account_ids"] == ["acc_123"]

    def test_tags_set_calls_api(self, mock_authenticated_client: MagicMock) -> None:
        """Tag assignment command calls set_transaction_tags."""
        captured: dict = {}

        async def async_set_tags(**kwargs):
            captured.update(kwargs)
            return {"success": True}

        mock_authenticated_client.set_transaction_tags = async_set_tags

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["tags", "set", "txn_123", "--tag", "tag_tax"])

            assert result.exit_code == 0
            assert captured == {"transaction_id": "txn_123", "tag_ids": ["tag_tax"]}

    def test_splits_update_reads_json(self, mock_authenticated_client: MagicMock) -> None:
        """Split update accepts JSON split data."""
        captured: dict = {}

        async def async_update_splits(**kwargs):
            captured.update(kwargs)
            return {"success": True}

        mock_authenticated_client.update_transaction_splits = async_update_splits

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
                    "splits",
                    "update",
                    "txn_123",
                    "--splits-json",
                    '[{"amount": 10, "category_id": "cat_1"}]',
                ],
            )

            assert result.exit_code == 0
            assert captured["transaction_id"] == "txn_123"
            assert captured["split_data"] == [{"amount": 10, "category_id": "cat_1"}]


class TestTransactionsAttach:
    """Tests for the transactions attach command."""

    def test_attach_uploads_file(
        self,
        mock_authenticated_client: MagicMock,
        tmp_path,
    ) -> None:
        """Attach uploads file bytes to the Monarch API."""
        receipt = tmp_path / "receipt.pdf"
        receipt.write_bytes(b"%PDF test receipt")
        upload_calls: list[dict] = []

        async def async_upload_attachment(**kwargs):
            upload_calls.append(kwargs)
            return {"addTransactionAttachment": {"attachment": {"id": "att_123"}}}

        mock_authenticated_client.upload_attachment = async_upload_attachment

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["attach", "txn_123", str(receipt)])

            assert result.exit_code == 0
            parsed = json.loads(result.stdout)
            assert parsed["status"] == "attached"
            assert parsed["transaction_id"] == "txn_123"
            assert parsed["filename"] == "receipt.pdf"
            assert parsed["notes_updated"] is False
            assert upload_calls == [
                {
                    "transaction_id": "txn_123",
                    "file_content": b"%PDF test receipt",
                    "filename": "receipt.pdf",
                }
            ]

    def test_attach_with_filename_and_notes(
        self,
        mock_authenticated_client: MagicMock,
        tmp_path,
    ) -> None:
        """Attach can override filename and update notes."""
        receipt = tmp_path / "local-name.png"
        receipt.write_bytes(b"png bytes")
        upload_calls: list[dict] = []
        update_calls: list[dict] = []

        async def async_upload_attachment(**kwargs):
            upload_calls.append(kwargs)
            return {"ok": True}

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs)
            return {"updated": True}

        mock_authenticated_client.upload_attachment = async_upload_attachment
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
                    "attach",
                    "txn_123",
                    str(receipt),
                    "--filename",
                    "merchant-receipt.png",
                    "--notes",
                    "Receipt: merchant, $12.34.",
                ],
            )

            assert result.exit_code == 0
            parsed = json.loads(result.stdout)
            assert parsed["filename"] == "merchant-receipt.png"
            assert parsed["notes_updated"] is True
            assert upload_calls[0]["filename"] == "merchant-receipt.png"
            assert update_calls == [
                {
                    "transaction_id": "txn_123",
                    "notes": "Receipt: merchant, $12.34.",
                }
            ]

    def test_attach_dry_run_does_not_authenticate(self, tmp_path) -> None:
        """Dry run validates the file and reports planned upload only."""
        receipt = tmp_path / "receipt.pdf"
        receipt.write_bytes(b"receipt")

        with (
            patch("monarch_cli.commands.transactions.get_authenticated_client") as auth,
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["attach", "txn_123", str(receipt), "--notes", "Receipt note", "--dry-run"],
            )

            assert result.exit_code == 0
            parsed = json.loads(result.stdout)
            assert parsed["status"] == "dry_run"
            assert parsed["filename"] == "receipt.pdf"
            assert parsed["notes"] == "Receipt note"
            auth.assert_not_called()

    def test_attach_missing_file_shows_typer_error(self) -> None:
        """Attach rejects missing files before authentication."""
        result = runner.invoke(app, ["attach", "txn_123", "/tmp/does-not-exist.pdf"])

        assert result.exit_code != 0
        assert "does not" in result.stderr.lower()
        assert "exist" in result.stderr.lower()

    def test_attach_help_shows_examples(self) -> None:
        """Attach --help shows examples."""
        result = runner.invoke(app, ["attach", "--help"])

        assert result.exit_code == 0
        import re

        output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "monarch transactions attach" in output
        assert "--filename" in output
        assert "--dry-run" in output


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
                app, ["batch-update", "txn_123", "txn_456", "--category", "cat_food"]
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "completed"
            assert output["success_count"] == 2
            assert output["failure_count"] == 0
            assert output["changes"]["category_id"] == "cat_food"
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
            result = runner.invoke(app, ["batch-update", "txn_123", "--notes", "Q1 Expenses"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "completed"
            assert output["success_count"] == 1
            assert output["changes"]["notes"] == "Q1 Expenses"

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
            assert output["success_count"] == 3
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
            assert output["success_count"] == 2
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
                ["batch-update", "txn_123", "txn_456", "txn_789", "--category", "cat_food"],
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "completed"
            assert output["success_count"] == 2
            assert output["failure_count"] == 1
            assert output["failures"] is not None
            assert len(output["failures"]) == 1
            assert output["failures"][0]["id"] == "txn_456"
            assert "API error" in output["failures"][0]["error"]

    def test_batch_update_no_ids_shows_error(self) -> None:
        """Batch update with no IDs shows error."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["batch-update", "--category", "cat_123"])

            assert result.exit_code == 1
            output = json.loads(result.stdout)
            assert output["status"] == "error"
            assert "No transaction IDs provided" in output["message"]

    def test_batch_update_no_changes_shows_error(self) -> None:
        """Batch update without changes shows error."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["batch-update", "txn_123"])

            assert result.exit_code == 1
            output = json.loads(result.stdout)
            assert output["status"] == "error"
            assert "No changes specified" in output["message"]

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
                ["batch-update", "txn_arg1", "--stdin", "--category", "cat_123"],
                input="txn_stdin1\ntxn_stdin2\n",
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["success_count"] == 3
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
