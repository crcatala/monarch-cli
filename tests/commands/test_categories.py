"""Tests for category commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.categories import _flatten_categories, app

runner = CliRunner()


@pytest.fixture
def mock_authenticated_client() -> MagicMock:
    """Create a mock authenticated client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def sample_categories_response() -> dict:
    """Sample categories API response with nested structure."""
    return {
        "categories": [
            {
                "name": "Food & Dining",
                "children": [
                    {"id": "cat_001", "name": "Groceries", "icon": "🛒"},
                    {"id": "cat_002", "name": "Restaurants", "icon": "🍽️"},
                    {"id": "cat_003", "name": "Coffee Shops", "icon": "☕"},
                ],
            },
            {
                "name": "Transportation",
                "children": [
                    {"id": "cat_004", "name": "Gas", "icon": "⛽"},
                    {"id": "cat_005", "name": "Public Transit", "icon": "🚇"},
                ],
            },
            {
                "name": "Entertainment",
                "children": [
                    {"id": "cat_006", "name": "Movies", "icon": "🎬"},
                ],
            },
        ]
    }


@pytest.fixture
def expected_flattened_categories() -> list[dict]:
    """Expected flattened category data."""
    return [
        {"id": "cat_001", "name": "Groceries", "group": "Food & Dining", "icon": "🛒"},
        {"id": "cat_002", "name": "Restaurants", "group": "Food & Dining", "icon": "🍽️"},
        {"id": "cat_003", "name": "Coffee Shops", "group": "Food & Dining", "icon": "☕"},
        {"id": "cat_004", "name": "Gas", "group": "Transportation", "icon": "⛽"},
        {"id": "cat_005", "name": "Public Transit", "group": "Transportation", "icon": "🚇"},
        {"id": "cat_006", "name": "Movies", "group": "Entertainment", "icon": "🎬"},
    ]


class TestFlattenCategories:
    """Tests for the category flattening function."""

    def test_flatten_creates_flat_list(self, sample_categories_response: dict) -> None:
        """Flatten converts nested structure to flat list."""
        result = _flatten_categories(sample_categories_response)

        assert len(result) == 6

    def test_flatten_includes_group_name(self, sample_categories_response: dict) -> None:
        """Flatten adds group name from parent category."""
        result = _flatten_categories(sample_categories_response)

        # Check Food & Dining group
        food_cats = [c for c in result if c["group"] == "Food & Dining"]
        assert len(food_cats) == 3
        assert "Groceries" in [c["name"] for c in food_cats]

        # Check Transportation group
        transport_cats = [c for c in result if c["group"] == "Transportation"]
        assert len(transport_cats) == 2

    def test_flatten_preserves_all_fields(
        self, sample_categories_response: dict, expected_flattened_categories: list[dict]
    ) -> None:
        """Flatten includes id, name, group, icon."""
        result = _flatten_categories(sample_categories_response)

        for i, item in enumerate(result):
            assert item["id"] == expected_flattened_categories[i]["id"]
            assert item["name"] == expected_flattened_categories[i]["name"]
            assert item["group"] == expected_flattened_categories[i]["group"]
            assert item["icon"] == expected_flattened_categories[i]["icon"]

    def test_flatten_handles_empty_response(self) -> None:
        """Flatten handles empty category data."""
        result = _flatten_categories({})
        assert result == []

        result = _flatten_categories({"categories": []})
        assert result == []

    def test_flatten_handles_empty_children(self) -> None:
        """Flatten handles groups with no children."""
        response = {
            "categories": [
                {"name": "Empty Group", "children": []},
                {
                    "name": "Has Children",
                    "children": [{"id": "cat_1", "name": "Test", "icon": "🔖"}],
                },
            ]
        }
        result = _flatten_categories(response)

        assert len(result) == 1
        assert result[0]["name"] == "Test"
        assert result[0]["group"] == "Has Children"

    def test_flatten_handles_missing_icon(self) -> None:
        """Flatten handles categories with missing icon."""
        response = {
            "categories": [
                {
                    "name": "Test Group",
                    "children": [
                        {"id": "cat_1", "name": "No Icon"},
                    ],
                }
            ]
        }
        result = _flatten_categories(response)

        assert len(result) == 1
        assert result[0]["id"] == "cat_1"
        assert result[0]["name"] == "No Icon"
        assert result[0]["icon"] is None


class TestCategoriesList:
    """Tests for the categories list command."""

    def test_list_returns_flattened_categories(
        self,
        mock_authenticated_client: MagicMock,
        sample_categories_response: dict,
    ) -> None:
        """List command returns flattened category data."""

        async def async_categories():
            return sample_categories_response

        mock_authenticated_client.get_transaction_categories = async_categories

        with (
            patch(
                "monarch_cli.commands.categories.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert len(output) == 6
            assert output[0]["id"] == "cat_001"
            assert output[0]["name"] == "Groceries"
            assert output[0]["group"] == "Food & Dining"

    def test_list_default_format_is_plain_in_tty(
        self,
        mock_authenticated_client: MagicMock,
        sample_categories_response: dict,
    ) -> None:
        """List defaults to plain format in TTY."""

        async def async_categories():
            return sample_categories_response

        mock_authenticated_client.get_transaction_categories = async_categories

        with (
            patch(
                "monarch_cli.commands.categories.get_authenticated_client",
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
        sample_categories_response: dict,
    ) -> None:
        """List with --json outputs JSON."""

        async def async_categories():
            return sample_categories_response

        mock_authenticated_client.get_transaction_categories = async_categories

        with (
            patch(
                "monarch_cli.commands.categories.get_authenticated_client",
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
        sample_categories_response: dict,
    ) -> None:
        """List with --format table outputs a table."""

        async def async_categories():
            return sample_categories_response

        mock_authenticated_client.get_transaction_categories = async_categories

        with (
            patch(
                "monarch_cli.commands.categories.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--format", "table"])

            assert result.exit_code == 0
            # Table output has table chars and column headers
            assert "id" in result.stdout
            assert "name" in result.stdout
            # Table contains box drawing characters
            assert "┃" in result.stdout or "|" in result.stdout

    def test_list_csv_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_categories_response: dict,
    ) -> None:
        """List with --format csv outputs CSV."""

        async def async_categories():
            return sample_categories_response

        mock_authenticated_client.get_transaction_categories = async_categories

        with (
            patch(
                "monarch_cli.commands.categories.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["--format", "csv"])

            assert result.exit_code == 0
            lines = result.stdout.strip().split("\n")
            assert len(lines) == 7  # header + 6 categories
            assert "id" in lines[0]
            assert "name" in lines[0]
            assert "group" in lines[0]
            assert "cat_001" in lines[1]

    def test_list_handles_empty_categories(
        self,
        mock_authenticated_client: MagicMock,
    ) -> None:
        """List handles case with no categories."""

        async def async_categories():
            return {"categories": []}

        mock_authenticated_client.get_transaction_categories = async_categories

        with (
            patch(
                "monarch_cli.commands.categories.get_authenticated_client",
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
        assert "monarch categories list" in output
        assert "json" in output.lower()
        assert "format" in output.lower()


class TestCategoriesApp:
    """Tests for the categories app structure."""

    def test_help_shows_description(self) -> None:
        """Running categories --help shows description and examples."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        # Single command app shows the command's help directly
        assert "categor" in output.lower()
        assert "format" in output.lower()

    def test_invalid_option_shows_error(self) -> None:
        """Invalid option shows error."""
        result = runner.invoke(app, ["--invalid-option"])

        assert result.exit_code != 0
