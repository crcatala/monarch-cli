"""Tests for account commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.accounts import app
from monarch_cli.output import set_quiet

runner = CliRunner()


@pytest.fixture
def mock_authenticated_client() -> MagicMock:
    """Create a mock authenticated client."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def sample_accounts_response() -> dict:
    """Sample accounts API response."""
    return {
        "accounts": [
            {
                "id": "acc_123",
                "displayName": "Chase Checking",
                "type": {"display": "Checking"},
                "subtype": {"display": "Checking"},
                "currentBalance": 1234.56,
                "institution": {"name": "Chase"},
                "isHidden": False,
                "isManual": False,
                "updatedAt": "2024-01-15T10:30:00Z",
            },
            {
                "id": "acc_456",
                "displayName": "Savings Account",
                "type": {"display": "Savings"},
                "subtype": {"display": "Savings"},
                "currentBalance": 5000.00,
                "institution": {"name": "Ally Bank"},
                "isHidden": False,
                "isManual": True,
                "updatedAt": "2024-01-14T09:00:00Z",
            },
        ]
    }


@pytest.fixture
def transformed_accounts() -> list[dict]:
    """Expected transformed accounts."""
    return [
        {
            "id": "acc_123",
            "name": "Chase Checking",
            "type": "Checking",
            "subtype": "Checking",
            "balance": 1234.56,
            "institution": "Chase",
            "is_active": True,
            "is_manual": False,
            "last_updated": "2024-01-15T10:30:00Z",
        },
        {
            "id": "acc_456",
            "name": "Savings Account",
            "type": "Savings",
            "subtype": "Savings",
            "balance": 5000.00,
            "institution": "Ally Bank",
            "is_active": True,
            "is_manual": True,
            "last_updated": "2024-01-14T09:00:00Z",
        },
    ]


class TestAccountsList:
    """Tests for the accounts list command."""

    def test_list_returns_transformed_accounts(self, transformed_accounts: list[dict]) -> None:
        """List command returns transformed accounts."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=transformed_accounts,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert len(output) == 2
            assert output[0]["id"] == "acc_123"
            assert output[0]["name"] == "Chase Checking"
            assert output[1]["id"] == "acc_456"

    def test_list_raw_returns_api_response(
        self, mock_authenticated_client: MagicMock, sample_accounts_response: dict
    ) -> None:
        """List with --raw returns raw API response."""

        async def async_accounts():
            return sample_accounts_response

        mock_authenticated_client.get_accounts = async_accounts

        with (
            patch(
                "monarch_cli.commands.accounts.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--raw", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert "accounts" in output
            assert len(output["accounts"]) == 2

    def test_list_ndjson_outputs_one_per_line(self, transformed_accounts: list[dict]) -> None:
        """List with --ndjson outputs one JSON object per line."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=transformed_accounts,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--ndjson"])

            assert result.exit_code == 0
            lines = result.stdout.strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["id"] == "acc_123"
            assert json.loads(lines[1])["id"] == "acc_456"

    def test_list_table_format(self, transformed_accounts: list[dict]) -> None:
        """List with --format table outputs a table."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=transformed_accounts,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--format", "table"])

            assert result.exit_code == 0
            # Table output has table chars and column headers
            assert "id" in result.stdout
            assert "name" in result.stdout
            # Table contains box drawing characters
            assert "┃" in result.stdout or "|" in result.stdout

    def test_list_csv_format(self, transformed_accounts: list[dict]) -> None:
        """List with --format csv outputs CSV."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=transformed_accounts,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--format", "csv"])

            assert result.exit_code == 0
            lines = result.stdout.strip().split("\n")
            assert len(lines) == 3  # header + 2 accounts
            assert "id" in lines[0]  # header
            assert "acc_123" in lines[1]

    def test_list_handles_empty_accounts(self) -> None:
        """List handles case with no accounts."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=[],
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output == []

    def test_list_quiet_mode_outputs_ids_only(self, transformed_accounts: list[dict]) -> None:
        """List with quiet mode outputs only account IDs."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=transformed_accounts,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            # Set quiet mode globally (simulates --quiet flag)
            set_quiet(True)
            try:
                result = runner.invoke(app, ["list"])

                assert result.exit_code == 0
                lines = result.stdout.strip().split("\n")
                assert len(lines) == 2
                assert lines[0] == "acc_123"
                assert lines[1] == "acc_456"
            finally:
                set_quiet(False)  # Cleanup

    def test_list_quiet_mode_empty_list(self) -> None:
        """Quiet mode with empty list produces no output."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_accounts",
                return_value=[],
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            set_quiet(True)
            try:
                result = runner.invoke(app, ["list"])

                assert result.exit_code == 0
                assert result.stdout.strip() == ""
            finally:
                set_quiet(False)

    def test_list_help_shows_examples(self) -> None:
        """List --help shows examples."""
        result = runner.invoke(app, ["list", "--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "monarch accounts list" in output
        assert "json" in output.lower()
        assert "format" in output.lower()


class TestAccountsRefresh:
    """Tests for the accounts refresh command."""

    def test_refresh_all_accounts(self) -> None:
        """Refresh without args refreshes all accounts."""
        refresh_result = {
            "status": "ok",
            "account_count": 3,
            "message": "Refresh requested for 3 account(s)",
        }

        with (
            patch(
                "monarch_cli.commands.accounts.refresh_accounts",
                return_value=refresh_result,
            ) as mock_refresh,
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["refresh"])

            assert result.exit_code == 0
            mock_refresh.assert_called_once_with(None)
            output = json.loads(result.stdout)
            assert output["status"] == "ok"
            assert output["account_count"] == 3

    def test_refresh_specific_accounts(self) -> None:
        """Refresh with -a flags refreshes specific accounts."""
        refresh_result = {
            "status": "ok",
            "account_count": 2,
            "message": "Refresh requested for 2 account(s)",
        }

        with (
            patch(
                "monarch_cli.commands.accounts.refresh_accounts",
                return_value=refresh_result,
            ) as mock_refresh,
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["refresh", "-a", "acc_123", "-a", "acc_456"])

            assert result.exit_code == 0
            mock_refresh.assert_called_once_with(["acc_123", "acc_456"])

    def test_refresh_no_accounts(self) -> None:
        """Refresh handles no accounts case."""
        refresh_result = {
            "status": "no_accounts",
            "account_count": 0,
            "message": "No accounts found to refresh",
        }

        with (
            patch(
                "monarch_cli.commands.accounts.refresh_accounts",
                return_value=refresh_result,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["refresh"])

            assert result.exit_code == 0
            output = json.loads(result.stdout)
            assert output["status"] == "no_accounts"

    def test_refresh_help_shows_examples(self) -> None:
        """Refresh --help shows examples."""
        result = runner.invoke(app, ["refresh", "--help"])

        assert result.exit_code == 0
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "monarch accounts refresh" in output
        assert "account" in output.lower()


class TestAccountsApp:
    """Tests for the accounts app structure."""

    def test_no_args_shows_help(self) -> None:
        """Running accounts with no args shows help (exit code 2 is expected)."""
        result = runner.invoke(app, [])

        # no_args_is_help causes exit code 2
        assert result.exit_code == 2
        # Strip ANSI codes for comparison
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "Account management" in output
        assert "list" in output
        assert "refresh" in output

    def test_invalid_command_shows_error(self) -> None:
        """Invalid command shows error."""
        result = runner.invoke(app, ["invalid"])

        assert result.exit_code != 0
