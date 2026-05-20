"""Tests for budget commands."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.budgets import _transform_budgets, app

runner = CliRunner()

# Current month for test fixtures
CURRENT_MONTH = date.today().replace(day=1).isoformat()


@pytest.fixture
def mock_authenticated_client() -> MagicMock:
    """Create a mock authenticated client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def sample_budgets_response() -> dict:
    """Sample budgets API response with monthlyAmountsByCategory structure."""
    return {
        "budgetData": {
            "monthlyAmountsByCategory": [
                {
                    "category": {"id": "cat_123", "__typename": "Category"},
                    "monthlyAmounts": [
                        {
                            "month": CURRENT_MONTH,
                            "plannedCashFlowAmount": 500.00,
                            "actualAmount": -350.00,  # Negative from API
                            "remainingAmount": 150.00,
                        },
                    ],
                },
                {
                    "category": {"id": "cat_456", "__typename": "Category"},
                    "monthlyAmounts": [
                        {
                            "month": CURRENT_MONTH,
                            "plannedCashFlowAmount": 200.00,
                            "actualAmount": -250.00,  # Over budget
                            "remainingAmount": -50.00,
                        },
                    ],
                },
                {
                    "category": {"id": "cat_789", "__typename": "Category"},
                    "monthlyAmounts": [
                        {
                            "month": CURRENT_MONTH,
                            "plannedCashFlowAmount": 300.00,
                            "actualAmount": 0,  # No spending
                            "remainingAmount": 300.00,
                        },
                    ],
                },
                {
                    "category": {"id": "cat_empty", "__typename": "Category"},
                    "monthlyAmounts": [
                        {
                            "month": CURRENT_MONTH,
                            "plannedCashFlowAmount": 0,  # No budget
                            "actualAmount": 0,  # No spending
                            "remainingAmount": 0,
                        },
                    ],
                },
            ]
        }
    }


@pytest.fixture
def expected_transformed_budgets() -> list[dict]:
    """Expected transformed budget data (excludes empty budgets)."""
    return [
        {
            "category_id": "cat_123",
            "budgeted": 500.00,
            "spent": 350.00,  # Absolute value
            "remaining": 150.00,
        },
        {
            "category_id": "cat_456",
            "budgeted": 200.00,
            "spent": 250.00,  # Absolute value
            "remaining": -50.00,
        },
        {
            "category_id": "cat_789",
            "budgeted": 300.00,
            "spent": 0,
            "remaining": 300.00,
        },
    ]


class TestTransformBudgets:
    """Tests for the budget transformation function."""

    def test_transform_converts_spent_to_absolute(self, sample_budgets_response: dict) -> None:
        """Transform converts negative spent amounts to positive."""
        result = _transform_budgets(sample_budgets_response)

        # Only 3 results (empty budget/spent excluded)
        assert len(result) == 3
        assert result[0]["spent"] == 350.00  # Was -350
        assert result[1]["spent"] == 250.00  # Was -250
        assert result[2]["spent"] == 0

    def test_transform_extracts_category_id(self, sample_budgets_response: dict) -> None:
        """Transform extracts category ID."""
        result = _transform_budgets(sample_budgets_response)

        assert result[0]["category_id"] == "cat_123"
        assert result[1]["category_id"] == "cat_456"
        assert result[2]["category_id"] == "cat_789"

    def test_transform_includes_all_fields(
        self, sample_budgets_response: dict, expected_transformed_budgets: list[dict]
    ) -> None:
        """Transform includes category_id, budgeted, spent, remaining."""
        result = _transform_budgets(sample_budgets_response)

        for i, item in enumerate(result):
            assert item["category_id"] == expected_transformed_budgets[i]["category_id"]
            assert item["budgeted"] == expected_transformed_budgets[i]["budgeted"]
            assert item["spent"] == expected_transformed_budgets[i]["spent"]
            assert item["remaining"] == expected_transformed_budgets[i]["remaining"]

    def test_transform_excludes_empty_budgets(self, sample_budgets_response: dict) -> None:
        """Transform excludes categories with no budget and no spending."""
        result = _transform_budgets(sample_budgets_response)

        # cat_empty should be excluded
        category_ids = [r["category_id"] for r in result]
        assert "cat_empty" not in category_ids
        assert len(result) == 3

    def test_transform_handles_empty_response(self) -> None:
        """Transform handles empty budget data."""
        result = _transform_budgets({})
        assert result == []

        result = _transform_budgets({"budgetData": {}})
        assert result == []

        result = _transform_budgets({"budgetData": {"monthlyAmountsByCategory": []}})
        assert result == []

    def test_transform_handles_missing_monthly_amounts(self) -> None:
        """Transform handles categories with missing monthly amounts."""
        response = {
            "budgetData": {
                "monthlyAmountsByCategory": [
                    {
                        "category": {"id": "cat_999"},
                        "monthlyAmounts": [],
                    }
                ]
            }
        }
        result = _transform_budgets(response)

        # No monthly amounts means nothing to show
        assert result == []

    def test_transform_uses_current_month(self) -> None:
        """Transform selects current month's data."""
        response = {
            "budgetData": {
                "monthlyAmountsByCategory": [
                    {
                        "category": {"id": "cat_001"},
                        "monthlyAmounts": [
                            {
                                "month": "2020-01-01",  # Old month
                                "plannedCashFlowAmount": 100.00,
                                "actualAmount": -50.00,
                                "remainingAmount": 50.00,
                            },
                            {
                                "month": CURRENT_MONTH,  # Current month
                                "plannedCashFlowAmount": 200.00,
                                "actualAmount": -75.00,
                                "remainingAmount": 125.00,
                            },
                        ],
                    }
                ]
            }
        }
        result = _transform_budgets(response)

        assert len(result) == 1
        assert result[0]["budgeted"] == 200.00  # Current month's value
        assert result[0]["spent"] == 75.00


class TestBudgetsList:
    """Tests for the budgets list command."""

    def test_list_returns_transformed_budgets(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """List command returns transformed budget data."""

        async def async_budgets():
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert len(output) == 3  # Excludes empty budget
            assert output[0]["category_id"] == "cat_123"
            assert output[0]["spent"] == 350.00  # Absolute value

    def test_list_plain_format_shows_formatted_output(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """List with --format plain shows human-readable output."""

        async def async_budgets():
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--format", "plain"])

            assert result.exit_code == 0
            # Plain format uses emoji icons
            assert "📊" in result.stdout  # Budgeted emoji
            assert "💸" in result.stdout  # Spent emoji

    def test_list_json_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """List with --json outputs JSON."""

        async def async_budgets():
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert isinstance(output, list)

    def test_list_table_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """List with --format table outputs a table."""

        async def async_budgets():
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--format", "table"])

            assert result.exit_code == 0
            # Table output has table chars and column headers
            assert "category_id" in result.stdout
            assert "budgeted" in result.stdout
            # Table contains box drawing characters
            assert "┃" in result.stdout or "|" in result.stdout

    def test_list_csv_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """List with --format csv outputs CSV."""

        async def async_budgets():
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--format", "csv"])

            assert result.exit_code == 0
            lines = result.stdout.strip().split("\n")
            assert len(lines) == 4  # header + 3 budgets (empty excluded)
            assert "category_id" in lines[0]
            assert "budgeted" in lines[0]
            assert "cat_123" in lines[1]

    def test_list_handles_empty_budgets(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """List handles case with no budgets."""

        async def async_budgets():
            return {"budgetData": {"monthlyAmountsByCategory": []}}

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output == []

    def test_list_help_shows_examples(self) -> None:
        """List --help shows examples."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "monarch budgets list" in output
        assert "json" in output.lower()
        assert "format" in output.lower()

    def test_list_accepts_explicit_date_range(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """Budget list passes explicit date range to API."""
        captured: dict = {}

        async def async_budgets(**kwargs):
            captured.update(kwargs)
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["--start", "2024-01-01", "--end", "2024-03-31", "--json"],
            )

            assert result.exit_code == 0
            assert captured["start_date"] == "2024-01-01"
            assert captured["end_date"] == "2024-03-31"


class TestBudgetMutations:
    """Tests for API-backed budget mutations."""

    def test_set_budget_amount(self, mock_authenticated_client: MagicMock) -> None:
        """Set command updates a category budget."""
        captured: dict = {}

        async def async_set_budget(**kwargs):
            captured.update(kwargs)
            return {"success": True}

        mock_authenticated_client.set_budget_amount = async_set_budget

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                [
                    "set",
                    "--amount",
                    "800",
                    "--category",
                    "cat_dining",
                    "--start",
                    "2024-06-01",
                    "--future",
                ],
            )

            assert result.exit_code == 0
            assert captured["amount"] == 800.0
            assert captured["category_id"] == "cat_dining"
            assert captured["start_date"] == "2024-06-01"
            assert captured["apply_to_future"] is True

    def test_flexible_budget_update(self, mock_authenticated_client: MagicMock) -> None:
        """Flexible budget command calls update_flexible_budget."""
        captured: dict = {}

        async def async_flexible(**kwargs):
            captured.update(kwargs)
            return {"success": True}

        mock_authenticated_client.update_flexible_budget = async_flexible

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["flexible", "--amount", "1200", "--future"])

            assert result.exit_code == 0
            assert captured["amount"] == 1200.0
            assert captured["apply_to_future"] is True


class TestBudgetsApp:
    """Tests for the budgets app structure."""

    def test_help_shows_description(self) -> None:
        """Running budgets --help shows description and examples."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        # Single command app shows the command's help directly
        assert "budget" in output.lower()
        assert "format" in output.lower()

    def test_invalid_option_shows_error(self) -> None:
        """Invalid option shows error."""
        result = runner.invoke(app, ["--invalid-option"])

        assert result.exit_code != 0
