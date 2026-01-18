"""Tests for budget commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.budgets import _transform_budgets, app

runner = CliRunner()


@pytest.fixture
def mock_authenticated_client() -> MagicMock:
    """Create a mock authenticated client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def sample_budgets_response() -> dict:
    """Sample budgets API response."""
    return {
        "budgetData": {
            "budgetItems": [
                {
                    "id": "budget_123",
                    "category": {"name": "Groceries"},
                    "budgetAmount": 500.00,
                    "spentAmount": -350.00,  # Negative from API
                    "remainingAmount": 150.00,
                },
                {
                    "id": "budget_456",
                    "category": {"name": "Entertainment"},
                    "budgetAmount": 200.00,
                    "spentAmount": -250.00,  # Over budget
                    "remainingAmount": -50.00,
                },
                {
                    "id": "budget_789",
                    "category": {"name": "Transportation"},
                    "budgetAmount": 300.00,
                    "spentAmount": 0,  # No spending
                    "remainingAmount": 300.00,
                },
            ]
        }
    }


@pytest.fixture
def expected_transformed_budgets() -> list[dict]:
    """Expected transformed budget data."""
    return [
        {
            "id": "budget_123",
            "category": "Groceries",
            "budgeted": 500.00,
            "spent": 350.00,  # Absolute value
            "remaining": 150.00,
        },
        {
            "id": "budget_456",
            "category": "Entertainment",
            "budgeted": 200.00,
            "spent": 250.00,  # Absolute value
            "remaining": -50.00,
        },
        {
            "id": "budget_789",
            "category": "Transportation",
            "budgeted": 300.00,
            "spent": 0,  # Absolute value of 0
            "remaining": 300.00,
        },
    ]


class TestTransformBudgets:
    """Tests for the budget transformation function."""

    def test_transform_converts_spent_to_absolute(self, sample_budgets_response: dict) -> None:
        """Transform converts negative spent amounts to positive."""
        result = _transform_budgets(sample_budgets_response)

        assert len(result) == 3
        assert result[0]["spent"] == 350.00  # Was -350
        assert result[1]["spent"] == 250.00  # Was -250
        assert result[2]["spent"] == 0  # Was 0

    def test_transform_extracts_category_name(self, sample_budgets_response: dict) -> None:
        """Transform flattens category to just the name."""
        result = _transform_budgets(sample_budgets_response)

        assert result[0]["category"] == "Groceries"
        assert result[1]["category"] == "Entertainment"
        assert result[2]["category"] == "Transportation"

    def test_transform_includes_all_fields(
        self, sample_budgets_response: dict, expected_transformed_budgets: list[dict]
    ) -> None:
        """Transform includes id, category, budgeted, spent, remaining."""
        result = _transform_budgets(sample_budgets_response)

        for i, item in enumerate(result):
            assert item["id"] == expected_transformed_budgets[i]["id"]
            assert item["category"] == expected_transformed_budgets[i]["category"]
            assert item["budgeted"] == expected_transformed_budgets[i]["budgeted"]
            assert item["spent"] == expected_transformed_budgets[i]["spent"]
            assert item["remaining"] == expected_transformed_budgets[i]["remaining"]

    def test_transform_handles_empty_response(self) -> None:
        """Transform handles empty budget data."""
        result = _transform_budgets({})
        assert result == []

        result = _transform_budgets({"budgetData": {}})
        assert result == []

        result = _transform_budgets({"budgetData": {"budgetItems": []}})
        assert result == []

    def test_transform_handles_missing_category(self) -> None:
        """Transform handles budget items with missing category."""
        response = {
            "budgetData": {
                "budgetItems": [
                    {
                        "id": "budget_999",
                        "budgetAmount": 100.00,
                        "spentAmount": -50.00,
                        "remainingAmount": 50.00,
                    }
                ]
            }
        }
        result = _transform_budgets(response)

        assert len(result) == 1
        assert result[0]["id"] == "budget_999"
        assert result[0]["category"] is None


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
            assert len(output) == 3
            assert output[0]["id"] == "budget_123"
            assert output[0]["category"] == "Groceries"
            assert output[0]["spent"] == 350.00  # Absolute value

    def test_list_default_format_is_plain_in_tty(
        self,
        mock_authenticated_client: MagicMock,
        sample_budgets_response: dict,
    ) -> None:
        """List defaults to plain format in TTY."""

        async def async_budgets():
            return sample_budgets_response

        mock_authenticated_client.get_budgets = async_budgets

        with (
            patch(
                "monarch_cli.commands.budgets.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
            patch("sys.stdout.isatty", return_value=True),
        ):
            result = runner.invoke(app, [])

            assert result.exit_code == 0
            # Plain format uses emoji icons
            assert "🔖" in result.stdout or "Groceries" in result.stdout

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
            assert "id" in result.stdout
            assert "category" in result.stdout
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
            assert len(lines) == 4  # header + 3 budgets
            assert "id" in lines[0]
            assert "category" in lines[0]
            assert "budget_123" in lines[1]

    def test_list_handles_empty_budgets(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """List handles case with no budgets."""

        async def async_budgets():
            return {"budgetData": {"budgetItems": []}}

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
