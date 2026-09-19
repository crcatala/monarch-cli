"""Tests for transaction commands."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.transactions import app
from monarch_cli.core.dates import parse_iso_date
from monarch_cli.core.exceptions import APIError, ValidationError
from monarch_cli.core.operations import reset_mutation_authorization, set_mutation_authorized
from monarch_cli.output import set_quiet

runner = CliRunner()


@pytest.fixture(autouse=True)
def authorize_subcommand_tests():
    """Sub-app tests bypass the root callback's global option parser."""
    set_mutation_authorized(True)
    yield
    reset_mutation_authorization()


class TestStrictDateParser:
    """The single shared strict YYYY-MM-DD validator used by the commands."""

    def test_parse_valid_date(self) -> None:
        from datetime import date

        result = parse_iso_date("2024-06-15", field="date")
        assert result == date(2024, 6, 15)

    def test_parse_none_returns_none(self) -> None:
        assert parse_iso_date(None, field="date") is None

    def test_parse_invalid_date_raises_structured_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            parse_iso_date("not-a-date", field="date")
        assert exc_info.value.code.value == "INVALID_INPUT"
        assert exc_info.value.exit_code == 2


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

    def test_list_malformed_root_reports_structured_api_error(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        """A non-object top-level payload is a typed APIError, not a traceback."""

        async def async_get_transactions(**_):
            return ["not", "an", "object"]

        mock_authenticated_client.get_transactions = async_get_transactions

        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 1
        error = json.loads(result.stderr[result.stderr.index("{") :])
        assert error["error"] is True
        assert error["code"] == "API_ERROR"
        assert error["details"]["expected"] == "object"
        assert error["details"]["received"] == "list"

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
            # Table output has table chars and column headers. The concise
            # display selection keeps owner attribution legible, so narrow
            # terminals may truncate individual headers (e.g. "da…" for date);
            # assert on stable prefixes rather than full header names.
            assert "id" in result.stdout
            assert "da" in result.stdout
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

    def test_list_maps_all_released_filters_and_tri_state_flags(
        self, mock_authenticated_client: MagicMock, sample_transactions_response: dict
    ) -> None:
        captured: dict[str, Any] = {}

        async def async_get_transactions(**kwargs: Any) -> dict:
            captured.update(kwargs)
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
                    "cat_1",
                    "--category",
                    "cat_2",
                    "--tag",
                    "tag_1",
                    "--has-attachments",
                    "--no-has-notes",
                    "--hidden-from-reports",
                    "--no-split",
                    "--recurring",
                    "--no-pending",
                    "--imported-from-mint",
                    "--no-synced-from-institution",
                    "--needs-review",
                    "--visibility",
                    "all_transactions",
                    "--json",
                ],
            )

        assert result.exit_code == 0
        assert captured == {
            "limit": 100,
            "offset": 0,
            "start_date": None,
            "end_date": None,
            "search": "",
            "account_ids": [],
            "category_ids": ["cat_1", "cat_2"],
            "tag_ids": ["tag_1"],
            "has_attachments": True,
            "has_notes": False,
            "hidden_from_reports": True,
            "is_split": False,
            "is_recurring": True,
            "is_pending": False,
            "imported_from_mint": True,
            "synced_from_institution": False,
            "needs_review": True,
            "transaction_visibility": "all_transactions",
        }

    @pytest.mark.parametrize(
        "args",
        [
            ["--limit", "0"],
            ["--limit", "1001"],
            ["--offset", "-1"],
            ["--start", "2024-02-01"],
            ["--start", "2024-02-02", "--end", "2024-02-01"],
        ],
    )
    def test_list_validation_happens_before_client_creation(self, args: list[str]) -> None:
        with patch("monarch_cli.commands.transactions.get_authenticated_client") as get_client:
            result = runner.invoke(app, ["list", *args, "--json"])
        assert result.exit_code == 2
        assert get_client.call_count == 0
        assert "INVALID_INPUT" in result.stderr


class TestTransactionsListOwnership:
    """Household ownership visibility in transaction list output.

    Normalized output always carries nullable ``owner_id``/``owner_name``
    plus a literal ``ownership_overridden_at``. Missing, null, or malformed
    owner payloads produce null owner fields; raw output remains untouched.
    """

    def _owned_transaction(self, owned_by: object, **extra: object) -> dict:
        txn: dict = {
            "id": "txn_owned",
            "date": "2026-01-15",
            "amount": -10.0,
            "merchant": {"name": "Coffee Shop"},
            "pending": False,
        }
        if owned_by is not None:
            txn["ownedByUser"] = owned_by
        txn.update(extra)
        return txn

    def _invoke_list_json(self, mock_authenticated_client: MagicMock, results: list[dict]):
        response = {"allTransactions": {"results": results}}

        async def async_get_transactions(**_):
            return response

        mock_authenticated_client.get_transactions = async_get_transactions
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            return runner.invoke(app, ["list", "--json"])

    def test_list_json_exposes_complete_owner(self, mock_authenticated_client: MagicMock) -> None:
        result = self._invoke_list_json(
            mock_authenticated_client,
            [self._owned_transaction({"id": "user-1", "name": "Alex"})],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload[0]["owner_id"] == "user-1"
        assert payload[0]["owner_name"] == "Alex"
        assert payload[0]["ownership_overridden_at"] is None

    @pytest.mark.parametrize(
        "owned_by",
        [None, "not-an-object", ["user-1"], {"id": "user-1"}, {"name": "Alex"}],
        ids=["null", "string", "list", "partial-id", "partial-name"],
    )
    def test_list_json_missing_or_malformed_owner_is_null(
        self, mock_authenticated_client: MagicMock, owned_by: object
    ) -> None:
        result = self._invoke_list_json(
            mock_authenticated_client, [self._owned_transaction(owned_by)]
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert "owner_id" in payload[0]
        assert "owner_name" in payload[0]
        assert "is_shared" not in payload[0]

    def test_list_json_override_timestamp_is_literal(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        result = self._invoke_list_json(
            mock_authenticated_client,
            [
                self._owned_transaction(
                    {"id": "user-1", "name": "Alex"},
                    ownershipOverriddenAt="2026-01-02T03:04:05Z",
                )
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload[0]["ownership_overridden_at"] == "2026-01-02T03:04:05Z"
        # The timestamp never grows derived actor/previous-owner/shared fields.
        assert "overridden_by" not in payload[0]
        assert "previous_owner" not in payload[0]
        assert "is_shared" not in payload[0]

    def test_list_quiet_remains_id_only(self, mock_authenticated_client: MagicMock) -> None:
        response = {"allTransactions": {"results": [self._owned_transaction({"id": "user-1"})]}}

        async def async_get_transactions(**_):
            return response

        mock_authenticated_client.get_transactions = async_get_transactions
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            set_quiet(True)
            try:
                result = runner.invoke(app, ["list"])
            finally:
                set_quiet(False)

        assert result.exit_code == 0
        assert result.stdout.strip() == "txn_owned"


class TestTransactionsGet:
    """Tests for normalized transaction detail discovery."""

    @pytest.fixture
    def sample_detail_response(self) -> dict[str, Any]:
        return {
            "getTransaction": {
                "id": "posted_123",
                "date": "2024-01-15",
                "amount": -50.0,
                "merchant": {"name": "Coffee Shop"},
                "pending": False,
                "needsReview": True,
                "reviewStatus": "PENDING",
                "reviewedAt": "2024-01-16T10:00:00Z",
                "reviewedByUser": {"id": "user_1", "name": "Alex"},
                "attachments": [{"id": "att_1", "filename": "receipt.pdf"}],
                "tags": [{"id": "tag_1", "name": "Work", "color": "blue"}],
                "isSplitTransaction": True,
                "hasSplitTransactions": True,
                "splitTransactions": [],
                "originalTransaction": {"id": "pending_123"},
            }
        }

    def test_get_normalizes_detail_and_exposes_redirect_identity(
        self, mock_authenticated_client: MagicMock, sample_detail_response: dict[str, Any]
    ) -> None:
        async def async_get_transaction_details(**kwargs: Any) -> dict[str, Any]:
            assert kwargs == {"transaction_id": "pending_123", "redirect_posted": True}
            return sample_detail_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "pending_123", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["requested_id"] == "pending_123"
        assert payload["id"] == "posted_123"
        assert payload["redirected"] is True
        assert payload["original_transaction"]["id"] == "pending_123"
        assert payload["is_pending"] is False
        assert payload["needs_review"] is True
        assert payload["review_status"] == "PENDING"
        assert payload["reviewed_at"] == "2024-01-16T10:00:00Z"
        assert payload["reviewed_by_user"] == {"id": "user_1", "name": "Alex"}
        assert payload["attachments"][0]["id"] == "att_1"
        assert payload["tags"][0]["name"] == "Work"

    def test_get_exposes_owner_fields_and_literal_override_timestamp(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        detail_response = {
            "getTransaction": {
                "id": "txn-detail",
                "date": "2024-01-15",
                "amount": -50.0,
                "ownedByUser": {"id": "user-1", "name": "Alex"},
                "ownershipOverriddenAt": "2026-01-02T03:04:05Z",
            }
        }

        async def async_get_transaction_details(**_kwargs: Any) -> dict[str, Any]:
            return detail_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "txn-detail", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["owner_id"] == "user-1"
        assert payload["owner_name"] == "Alex"
        assert payload["ownership_overridden_at"] == "2026-01-02T03:04:05Z"
        # The timestamp never grows derived actor/previous-owner/shared fields.
        assert "overridden_by" not in payload
        assert "previous_owner" not in payload
        assert "is_shared" not in payload

    @pytest.mark.parametrize(
        "owned_by",
        [None, "not-an-object", ["user-1"], {}],
        ids=["null", "string", "list", "empty-object"],
    )
    def test_get_malformed_owner_yields_nulls_without_crashing(
        self, mock_authenticated_client: MagicMock, owned_by: object
    ) -> None:
        detail_response = {
            "getTransaction": {
                "id": "txn-detail",
                "date": "2024-01-15",
                "amount": -50.0,
                "ownedByUser": owned_by,
            }
        }

        async def async_get_transaction_details(**_kwargs: Any) -> dict[str, Any]:
            return detail_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "txn-detail", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["owner_id"] is None
        assert payload["owner_name"] is None
        assert payload["ownership_overridden_at"] is None

    def test_get_preserves_needs_review_when_detail_omits_review_status(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        """Released public detail responses may omit opaque reviewStatus."""
        detail_response = {
            "getTransaction": {
                "id": "txn-detail",
                "date": "2024-01-15",
                "amount": -50.0,
                "merchant": {"name": "Coffee Shop"},
                "pending": False,
                "needsReview": True,
                "attachments": [],
                "tags": [],
                "isSplitTransaction": False,
                "splitTransactions": [],
            }
        }

        async def async_get_transaction_details(**_: Any) -> dict[str, Any]:
            return detail_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "txn-detail", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["needs_review"] is True
        assert payload["review_status"] is None

    def test_get_strict_disables_posted_redirect(
        self, mock_authenticated_client: MagicMock, sample_detail_response: dict[str, Any]
    ) -> None:
        captured: dict[str, Any] = {}

        async def async_get_transaction_details(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return sample_detail_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "pending_123", "--strict", "--json"])

        assert result.exit_code == 0
        assert captured == {"transaction_id": "pending_123", "redirect_posted": False}

    def test_get_raw_preserves_upstream_envelope(
        self, mock_authenticated_client: MagicMock, sample_detail_response: dict[str, Any]
    ) -> None:
        async def async_get_transaction_details(**_: Any) -> dict[str, Any]:
            return sample_detail_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "pending_123", "--raw", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == sample_detail_response

    @pytest.mark.parametrize("raw_response", [{"getTransaction": None}, {}])
    def test_get_not_found_is_structured_error(
        self, mock_authenticated_client: MagicMock, raw_response: dict[str, Any]
    ) -> None:
        async def async_get_transaction_details(**_: Any) -> dict[str, Any]:
            return raw_response

        mock_authenticated_client.get_transaction_details = async_get_transaction_details
        with (
            patch(
                "monarch_cli.commands.transactions.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["get", "missing", "--json"])

        assert result.exit_code == 1
        assert '"code": "NOT_FOUND"' in result.stderr


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
            result = runner.invoke(
                app, ["update", "--transaction-id", "txn_123", "--amount", "25.50"]
            )

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
            result = runner.invoke(
                app, ["update", "--transaction-id", "txn_123", "--notes", "Review"]
            )

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
            result = runner.invoke(
                app, ["update", "--transaction-id", "txn_123", "--notes", "Review"]
            )

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
                ["update", "--transaction-id", "txn_123", "--description", "Coffee Shop"],
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
                ["update", "--transaction-id", "txn_123", "--category", "cat_456"],
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
                ["update", "--transaction-id", "txn_123", "--notes", "Business lunch"],
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
                    "--transaction-id",
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
            result = runner.invoke(
                app, ["update", "--transaction-id", "txn_123", "--amount", "25.50", "--dry-run"]
            )

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "dry_run"
            assert output["transaction_id"] == "txn_123"
            assert output["changes"]["amount"] == 25.50
            assert "No changes applied" in output["message"]

    def test_update_no_changes_uses_structured_error_contract(self) -> None:
        """A pre-execution validation failure is a structured error, not an outcome."""
        with patch("monarch_cli.output.progress.is_interactive", return_value=False):
            result = runner.invoke(app, ["update", "--transaction-id", "txn_123"])

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
                    "--transaction-id",
                    "txn_123",
                    "--transaction-id",
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
                ["batch-update", "--transaction-id", "txn_123", "--notes", "Q1 Expenses"],
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
                [
                    "batch-update",
                    "--transaction-id",
                    "txn_123",
                    "--transaction-id",
                    "txn_456",
                    "--category",
                    "cat_food",
                    "--dry-run",
                ],
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
                    "--transaction-id",
                    "txn_123",
                    "--transaction-id",
                    "txn_456",
                    "--transaction-id",
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
                    "--transaction-id",
                    "txn_123",
                    "--transaction-id",
                    "txn_456",
                    "--transaction-id",
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
            result = runner.invoke(app, ["batch-update", "--transaction-id", "txn_123"])

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
                    "--transaction-id",
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
                [
                    "batch-update",
                    "--transaction-id",
                    "txn_1",
                    "--transaction-id",
                    "txn_2",
                    "--category",
                    "cat_food",
                ],
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


class TestExplicitMutationTargets:
    """Removed positional mutation targets report actionable errors (mc-vv11)."""

    def test_update_rejects_removed_positional_id(self) -> None:
        result = runner.invoke(app, ["update", "txn_123", "--amount", "5"])
        assert result.exit_code != 0
        assert "transaction-id" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    def test_update_positional_with_option_reports_removal(self) -> None:
        result = runner.invoke(
            app, ["update", "--transaction-id", "txn_1", "txn_2", "--amount", "5"]
        )
        assert result.exit_code == 2
        assert "no longer supported" in result.output.lower()

    def test_update_empty_transaction_id_is_validation_error(self) -> None:
        result = runner.invoke(app, ["update", "--transaction-id", "  ", "--amount", "5"])
        assert result.exit_code == 2
        assert "must not be empty" in result.output.lower()

    def test_batch_rejects_removed_positional_ids(self) -> None:
        result = runner.invoke(app, ["batch-update", "txn_123", "--notes", "x"])
        assert result.exit_code != 0
        assert "transaction-id" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    def test_batch_positional_with_option_reports_removal(self) -> None:
        result = runner.invoke(
            app, ["batch-update", "--transaction-id", "txn_1", "txn_2", "--notes", "x"]
        )
        assert result.exit_code == 2
        assert "no longer supported" in result.output.lower()

    def test_batch_missing_ids_is_validation_error(self) -> None:
        result = runner.invoke(app, ["batch-update", "--notes", "x"])
        assert result.exit_code == 2
        assert "No transaction IDs provided" in result.output

    def test_batch_empty_id_is_validation_error(self) -> None:
        result = runner.invoke(app, ["batch-update", "--transaction-id", "", "--notes", "x"])
        assert result.exit_code == 2
        assert "must not be empty" in result.output.lower()

    def test_batch_dedupes_options_then_stdin_first_seen(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """Repeatable options are consumed before stdin, deduped first-seen."""
        update_calls: list[str] = []

        async def async_update_transaction(**kwargs):
            update_calls.append(kwargs["transaction_id"])
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
                    "--transaction-id",
                    "txn_1",
                    "--transaction-id",
                    "txn_1",
                    "--transaction-id",
                    "txn_2",
                    "--stdin",
                    "--notes",
                    "x",
                ],
                input="txn_2\ntxn_3\n",
            )

        assert result.exit_code == 0, result.output
        assert update_calls == ["txn_1", "txn_2", "txn_3"]


class TestValidationSemantics:
    """mc-s6s6: early, structured validation of flags and values."""

    def test_batch_max_concurrency_rejects_zero(self) -> None:
        result = runner.invoke(
            app,
            ["batch-update", "--transaction-id", "txn_1", "--max-concurrency", "0", "--notes", "x"],
        )
        assert result.exit_code == 2
        assert json.loads(result.stderr)["code"] == "INVALID_INPUT"

    @pytest.mark.parametrize("value", ["-3", "17", "100"])
    def test_batch_max_concurrency_rejects_out_of_range(self, value: str) -> None:
        result = runner.invoke(
            app,
            [
                "batch-update",
                "--transaction-id",
                "txn_1",
                "--max-concurrency",
                value,
                "--notes",
                "x",
            ],
        )
        assert result.exit_code == 2
        assert json.loads(result.stderr)["code"] == "INVALID_INPUT"

    def test_update_rejects_non_finite_amounts(self) -> None:
        for value in ("nan", "inf", "-inf"):
            result = runner.invoke(
                app, ["update", "--transaction-id", "txn_1", "--amount", value, "--dry-run"]
            )
            assert result.exit_code == 2, (value, result.output)
            assert json.loads(result.stderr)["code"] == "INVALID_INPUT"

    def test_update_allows_zero_amount(self) -> None:
        result = runner.invoke(
            app, ["update", "--transaction-id", "txn_1", "--amount", "0", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["changes"]["amount"] == 0.0

    @pytest.mark.parametrize("value", ["20240115", "2024-1-5", "01-15-2024"])
    def test_update_date_uses_strict_parser(self, value: str) -> None:
        result = runner.invoke(
            app, ["update", "--transaction-id", "txn_1", "--date", value, "--dry-run"]
        )
        assert result.exit_code == 2, (value, result.output)
        assert json.loads(result.stderr)["code"] == "INVALID_INPUT"

    @pytest.mark.parametrize("value", ["20240115", "2024-1-5"])
    def test_list_date_uses_strict_parser(self, value: str) -> None:
        result = runner.invoke(app, ["list", "--start", value])
        assert result.exit_code == 2
        assert json.loads(result.stderr)["code"] == "INVALID_INPUT"
