"""Tests for cashflow commands."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.cashflow import _parse_date, app

runner = CliRunner()


@pytest.fixture
def mock_authenticated_client() -> MagicMock:
    """Create a mock authenticated client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def sample_cashflow_response() -> dict:
    """Sample cashflow summary API response (nested structure from API)."""
    return {
        "summary": [
            {
                "summary": {
                    "sumIncome": 5000.00,
                    "sumExpense": -3500.00,
                    "savings": 1500.00,
                    "savingsRate": 30.0,
                    "__typename": "TransactionsSummary",
                },
                "__typename": "AggregateData",
            }
        ]
    }


class TestParseDateHelper:
    """Tests for the date parsing helper."""

    def test_parse_valid_date(self) -> None:
        """Parse valid date string."""
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


class TestCashflowSummary:
    """Tests for the cashflow summary command."""

    def test_summary_returns_transformed_cashflow_data(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary command returns transformed cashflow data."""

        async def async_cashflow(**_kwargs):
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.stdout)
            # Transformed output uses snake_case and positive expenses
            assert data["income"] == 5000.00
            assert data["expenses"] == 3500.00  # Converted to positive
            assert data["savings"] == 1500.00
            assert data["savings_rate"] == 30.0

    def test_summary_plain_format_shows_formatted_output(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary with --format plain shows human-readable output."""

        async def async_cashflow(**_kwargs):
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--format", "plain"])

            assert result.exit_code == 0
            # Plain format uses emoji icons and field names
            assert "📈" in result.stdout  # Income emoji
            assert "📉" in result.stdout  # Expenses emoji
            assert "5,000" in result.stdout or "5000" in result.stdout

    def test_summary_with_preset(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary with --preset passes dates to API."""
        captured_kwargs: dict = {}

        async def async_cashflow(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--preset", "this-month", "--json"])

            assert result.exit_code == 0
            # Preset should resolve to dates
            assert captured_kwargs.get("start_date") is not None
            assert captured_kwargs.get("end_date") is not None

    def test_summary_with_explicit_dates(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary with explicit --start and --end dates."""
        captured_kwargs: dict = {}

        async def async_cashflow(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["summary", "--start", "2024-01-01", "--end", "2024-12-31", "--json"],
            )

            assert result.exit_code == 0
            assert captured_kwargs.get("start_date") == "2024-01-01"
            assert captured_kwargs.get("end_date") == "2024-12-31"

    def test_summary_explicit_dates_override_preset(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Explicit dates override preset dates."""
        captured_kwargs: dict = {}

        async def async_cashflow(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            # Use preset but override start date
            result = runner.invoke(
                app,
                [
                    "summary",
                    "--preset",
                    "this-month",
                    "--start",
                    "2024-06-15",
                    "--end",
                    "2024-06-30",
                    "--json",
                ],
            )

            assert result.exit_code == 0
            # Explicit start should override preset's start
            assert captured_kwargs.get("start_date") == "2024-06-15"

    def test_summary_json_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary with --json outputs transformed JSON."""

        async def async_cashflow(**_kwargs):
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert isinstance(output, dict)
            # Transformed output uses snake_case keys
            assert "income" in output
            assert "expenses" in output
            assert "savings" in output
            assert "savings_rate" in output

    def test_summary_table_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary with --format table outputs (falls back to JSON for dict data)."""

        async def async_cashflow(**_kwargs):
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--format", "table"])

            assert result.exit_code == 0
            # Table format falls back to JSON for non-list data (dicts)
            # This is expected behavior - cashflow summary is a dict, not list
            output = json.loads(result.stdout)
            # Transformed output uses snake_case keys
            assert "income" in output

    def test_summary_csv_format(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary with --format csv falls back to JSON for dict data."""

        async def async_cashflow(**_kwargs):
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--format", "csv"])

            assert result.exit_code == 0
            # CSV format falls back to JSON for non-list data (dicts)
            output = json.loads(result.stdout)
            # Transformed output uses snake_case keys
            assert "income" in output

    def test_summary_help_shows_examples(self) -> None:
        """Summary --help shows examples."""
        result = runner.invoke(app, ["summary", "--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "monarch cashflow summary" in output
        assert "preset" in output.lower()
        assert "this-month" in output

    def test_summary_without_dates(
        self,
        mock_authenticated_client: MagicMock,
        sample_cashflow_response: dict,
    ) -> None:
        """Summary without dates passes None."""
        captured_kwargs: dict = {}

        async def async_cashflow(**kwargs):
            captured_kwargs.update(kwargs)
            return sample_cashflow_response

        mock_authenticated_client.get_cashflow_summary = async_cashflow

        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["summary", "--json"])

            assert result.exit_code == 0
            assert captured_kwargs.get("start_date") is None
            assert captured_kwargs.get("end_date") is None


class TestCashflowDetail:
    """Tests for the single-request aggregate detail command."""

    @pytest.fixture
    def sample_detail_response(self) -> dict:
        return {
            "byCategory": [
                {
                    "groupBy": {
                        "category": {
                            "id": "cat-1",
                            "name": "Food",
                            "group": {"id": "g-1", "type": "needs"},
                        }
                    },
                    "summary": [{"sum": -10.0}],
                }
            ],
            "byCategoryGroup": [],
            "byMerchant": [],
            "summary": [
                {
                    "summary": {
                        "sumIncome": 20.0,
                        "sumExpense": -10.0,
                        "savings": 10.0,
                        "savingsRate": 50.0,
                    }
                }
            ],
        }

    def test_detail_uses_get_cashflow_once_and_normalizes(
        self, mock_authenticated_client: MagicMock, sample_detail_response: dict
    ) -> None:
        captured: dict = {}

        async def async_cashflow(**kwargs):
            captured.update(kwargs)
            return sample_detail_response

        mock_authenticated_client.get_cashflow = async_cashflow
        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app, ["detail", "--start", "2024-01-01", "--end", "2024-01-31", "--json"]
            )

        assert result.exit_code == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["summary"]["income"] == 20.0
        assert captured == {"start_date": "2024-01-01", "end_date": "2024-01-31"}

    def test_detail_preset_resolves_both_bounds(
        self, mock_authenticated_client: MagicMock, sample_detail_response: dict
    ) -> None:
        captured: dict = {}

        async def async_cashflow(**kwargs):
            captured.update(kwargs)
            return sample_detail_response

        mock_authenticated_client.get_cashflow = async_cashflow
        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["detail", "--preset", "this-month", "--json"])

        assert result.exit_code == 0
        assert captured["start_date"] is not None
        assert captured["end_date"] is not None

    @pytest.mark.parametrize(
        "args",
        [
            ["detail", "--start", "2024-01-01"],
            ["detail", "--end", "2024-01-31"],
            ["detail", "--start", "2024-02-01", "--end", "2024-01-31"],
            ["detail", "--start", "not-a-date", "--end", "2024-01-31"],
        ],
    )
    def test_invalid_dates_fail_before_client_creation(self, args: list[str]) -> None:
        with patch("monarch_cli.commands.cashflow.get_authenticated_client") as get_client:
            result = runner.invoke(app, [*args, "--json"])

        assert result.exit_code == 2
        get_client.assert_not_called()
        assert "INVALID_INPUT" in result.stderr

    def test_raw_preserves_response_and_does_not_request_summary(
        self, mock_authenticated_client: MagicMock, sample_detail_response: dict
    ) -> None:
        async def async_cashflow(**_kwargs):
            return sample_detail_response

        mock_authenticated_client.get_cashflow = async_cashflow
        mock_authenticated_client.get_cashflow_summary = MagicMock()
        with (
            patch(
                "monarch_cli.commands.cashflow.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["detail", "--raw", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == sample_detail_response
        mock_authenticated_client.get_cashflow_summary.assert_not_called()


class TestCashflowApp:
    """Tests for the cashflow app structure."""

    def test_app_help_shows_description(self) -> None:
        """Running cashflow --help shows description."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        output = result.stdout.lower()
        assert "cashflow analysis" in output
        assert "summary" in output
        assert "detail" in output

    def test_no_args_runs_command(self) -> None:
        """The cashflow group exposes summary and detail subcommands."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        output = result.stdout.lower()
        assert "summary" in output
        assert "detail" in output

    def test_invalid_option_shows_error(self) -> None:
        """Invalid option shows error."""
        result = runner.invoke(app, ["summary", "--invalid-option-xyz"])

        assert result.exit_code != 0
