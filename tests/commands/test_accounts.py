"""Tests for account commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.accounts import app
from monarch_cli.core.operations import (
    Effect,
    Operation,
    reset_mutation_authorization,
    set_mutation_authorized,
)
from monarch_cli.output import set_quiet
from monarch_cli.transformers.accounts import ACCOUNT_TYPE_RECORD_FIELDS

runner = CliRunner()


@pytest.fixture(autouse=True)
def authorize_subcommand_tests():
    """Sub-app tests bypass the root callback's global option parser."""
    set_mutation_authorized(True)
    yield
    reset_mutation_authorization()


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

    def test_list_raw_preserves_null_and_unknown_fields(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        """Raw mode bypasses normalization: null containers and unknown fields survive."""
        raw_response = {"accounts": None, "futureField": {"nested": 1}, "count": 0}

        async def async_accounts():
            return raw_response

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
            assert json.loads(result.stdout) == raw_response

    def test_list_malformed_root_reports_structured_api_error(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        """A non-object top-level payload is a typed APIError, not a traceback."""

        async def async_accounts():
            return ["not", "an", "object"]

        mock_authenticated_client.get_accounts = async_accounts

        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
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


SAMPLE_TYPE_OPTIONS_RAW = {
    "accountTypeOptions": [
        {
            "type": {
                "name": "asset",
                "display": "Asset",
                "group": "assets",
                "possibleSubtypes": [
                    {"name": "checking", "display": "Checking"},
                    {"name": "savings", "display": "Savings"},
                ],
            },
            "subtype": None,
        },
        {
            "type": {
                "name": "loan",
                "display": "Loan",
                "group": "liabilities",
                "possibleSubtypes": [
                    {"name": "mortgage", "display": "Mortgage"},
                ],
            },
            "subtype": None,
        },
    ]
}

SAMPLE_TYPE_RECORDS = [
    {
        "group": "assets",
        "type": "asset",
        "type_display": "Asset",
        "subtype": "checking",
        "subtype_display": "Checking",
    },
    {
        "group": "assets",
        "type": "asset",
        "type_display": "Asset",
        "subtype": "savings",
        "subtype_display": "Savings",
    },
    {
        "group": "liabilities",
        "type": "loan",
        "type_display": "Loan",
        "subtype": "mortgage",
        "subtype_display": "Mortgage",
    },
]


class TestAccountsTypes:
    """Tests for the accounts types command."""

    def test_types_returns_normalized_records(self) -> None:
        """Types command returns normalized account type records."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_account_types",
                return_value=SAMPLE_TYPE_RECORDS,
            ) as mock_types,
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--json"])

            assert result.exit_code == 0
            mock_types.assert_called_once_with(
                Operation(command="accounts types", effects=frozenset({Effect.READ_ONLY}))
            )
            output = json.loads(result.stdout)
            assert len(output) == 3
            assert output[0] == {
                "group": "assets",
                "type": "asset",
                "type_display": "Asset",
                "subtype": "checking",
                "subtype_display": "Checking",
            }

    def test_types_preserves_upstream_order(self) -> None:
        """Types command output keeps the service's deterministic order."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_account_types",
                return_value=SAMPLE_TYPE_RECORDS,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--json"])

            output = json.loads(result.stdout)
            assert [(r["type"], r["subtype"]) for r in output] == [
                ("asset", "checking"),
                ("asset", "savings"),
                ("loan", "mortgage"),
            ]

    def test_types_raw_returns_api_response(self, mock_authenticated_client: MagicMock) -> None:
        """Types with --raw returns the untouched API response."""

        async def async_type_options():
            return SAMPLE_TYPE_OPTIONS_RAW

        mock_authenticated_client.get_account_type_options = async_type_options

        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--raw", "--json"])

            assert result.exit_code == 0
            assert json.loads(result.stdout) == SAMPLE_TYPE_OPTIONS_RAW

    def test_types_table_format(self) -> None:
        """Types with --format table outputs a table."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_account_types",
                return_value=SAMPLE_TYPE_RECORDS,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--format", "table"])

            assert result.exit_code == 0
            for field in ACCOUNT_TYPE_RECORD_FIELDS:
                assert field in result.stdout

    def test_types_csv_format(self) -> None:
        """Types with --format csv outputs CSV rows."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_account_types",
                return_value=SAMPLE_TYPE_RECORDS,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--format", "csv"])

            assert result.exit_code == 0
            lines = result.stdout.strip().split("\n")
            assert len(lines) == 4  # header + 3 records
            assert "group" in lines[0]
            assert "assets" in lines[1]

    def test_types_handles_empty_options(self) -> None:
        """Types handles the empty option set."""
        with (
            patch(
                "monarch_cli.commands.accounts.list_account_types",
                return_value=[],
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--json"])

            assert result.exit_code == 0
            assert json.loads(result.stdout) == []

    def test_types_malformed_root_reports_structured_api_error(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        """A non-object top-level payload is a typed APIError, not a traceback."""

        async def async_type_options():
            return ["not", "an", "object"]

        mock_authenticated_client.get_account_type_options = async_type_options

        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["types", "--json"])

        assert result.exit_code == 1
        error = json.loads(result.stderr[result.stderr.index("{") :])
        assert error["error"] is True
        assert error["code"] == "API_ERROR"
        assert error["details"]["expected"] == "object"

    def test_types_does_not_require_mutation_authorization(self) -> None:
        """The read-only command runs without --allow-mutations authorization."""
        reset_mutation_authorization()
        try:
            with (
                patch(
                    "monarch_cli.commands.accounts.list_account_types",
                    return_value=[],
                ),
                patch("monarch_cli.output.progress.is_interactive", return_value=False),
            ):
                result = runner.invoke(app, ["types", "--json"])

                assert result.exit_code == 0
                assert json.loads(result.stdout) == []
        finally:
            set_mutation_authorized(True)

    def test_types_help_shows_examples(self) -> None:
        """Types --help shows examples."""
        result = runner.invoke(app, ["types", "--help"])

        assert result.exit_code == 0
        output = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "monarch accounts types" in output
        assert "raw" in output.lower()


class TestAccountsRefresh:
    """Tests for the accounts refresh command."""

    def test_refresh_all_accounts(self) -> None:
        """Refresh without args refreshes all accounts."""
        refresh_result = {
            "schema_version": "mutation-outcome.v1",
            "operation": "accounts.refresh",
            "status": "succeeded",
            "summary": {"total": 3, "succeeded": 3, "failed": 0, "ambiguous": 0},
            "items": [
                {
                    "entity": "account",
                    "id": f"acc_{i}",
                    "status": "succeeded",
                    "result": {},
                    "error": None,
                }
                for i in range(3)
            ],
            "verification": None,
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
            mock_refresh.assert_called_once_with(
                None,
                operation=Operation(
                    command="accounts refresh",
                    effects=frozenset({Effect.REMOTE_MUTATION}),
                ),
            )
            output = json.loads(result.stdout)
            assert output["schema_version"] == "mutation-outcome.v1"
            assert output["status"] == "succeeded"
            assert output["summary"]["total"] == 3

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
            result = runner.invoke(
                app,
                ["refresh", "-a", "acc_123", "-a", "acc_456"],
            )

            assert result.exit_code == 0
            mock_refresh.assert_called_once_with(
                ["acc_123", "acc_456"],
                operation=Operation(
                    command="accounts refresh",
                    effects=frozenset({Effect.REMOTE_MUTATION}),
                ),
            )

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

    def test_refresh_ambiguous_outcome_exits_four(self) -> None:
        """An ambiguous refresh outcome exits 4 with the envelope on stdout."""
        refresh_result = {
            "schema_version": "mutation-outcome.v1",
            "operation": "accounts.refresh",
            "status": "ambiguous",
            "summary": {"total": 1, "succeeded": 0, "failed": 0, "ambiguous": 1},
            "items": [
                {
                    "entity": "account",
                    "id": "acc_123",
                    "status": "ambiguous",
                    "result": None,
                    "error": {
                        "code": "MUTATION_AMBIGUOUS",
                        "message": "outcome unknown",
                        "details": {},
                    },
                }
            ],
            "verification": {
                "required": True,
                "message": "Verify the account in the Monarch web UI.",
                "command": None,
            },
        }

        with (
            patch(
                "monarch_cli.commands.accounts.refresh_accounts",
                return_value=refresh_result,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["refresh"])

            assert result.exit_code == 4
            output = json.loads(result.stdout)
            assert output["status"] == "ambiguous"
            assert output["verification"]["required"] is True

    def test_refresh_failed_outcome_exits_one(self) -> None:
        """A definitive refresh failure exits with the normal error code."""
        refresh_result = {
            "schema_version": "mutation-outcome.v1",
            "operation": "accounts.refresh",
            "status": "failed",
            "summary": {"total": 1, "succeeded": 0, "failed": 1, "ambiguous": 0},
            "items": [
                {
                    "entity": "account",
                    "id": "acc_123",
                    "status": "failed",
                    "result": None,
                    "error": {
                        "code": "API_ERROR",
                        "message": "The refresh request was not accepted by the service.",
                        "details": {},
                    },
                }
            ],
            "verification": None,
        }

        with (
            patch(
                "monarch_cli.commands.accounts.refresh_accounts",
                return_value=refresh_result,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["refresh"])

            assert result.exit_code == 1
            output = json.loads(result.stdout)
            assert output["status"] == "failed"
            assert output["verification"] is None

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
