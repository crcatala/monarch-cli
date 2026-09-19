"""Tests for account commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from monarch_cli.commands.accounts import ACCOUNT_LIST_DISPLAY_FIELDS, app
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
            # Table output has table chars and column headers. The concise
            # display selection keeps liability classification (is_asset) and
            # owner attribution legible, so narrow terminals may truncate
            # individual headers; assert on stable prefixes rather than full
            # header names.
            assert "id" in result.stdout
            assert "apr" in result.stdout
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


class TestAccountsListOwnership:
    """Household ownership visibility in account list output.

    Normalized output always carries nullable ``owner_id``/``owner_name``
    sourced from the upstream ``ownedByUser`` relationship. Missing, null,
    or malformed owner payloads produce null owner fields — never an
    invented shared/unassigned label. Raw output remains untouched.
    """

    def test_list_json_exposes_complete_owner(self, mock_authenticated_client: MagicMock) -> None:
        response = {
            "accounts": [
                {
                    "id": "acc_123",
                    "displayName": "Chase Checking",
                    "ownedByUser": {"id": "user-1", "displayName": "Alex"},
                }
            ]
        }

        async def async_accounts() -> dict:
            return response

        mock_authenticated_client.get_accounts = async_accounts
        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload[0]["owner_id"] == "user-1"
        assert payload[0]["owner_name"] == "Alex"

    @pytest.mark.parametrize(
        "owned_by",
        [None, "not-an-object", ["user-1"], {"id": "user-1"}, {"displayName": "Alex"}],
        ids=["null", "string", "list", "partial-id", "partial-name"],
    )
    def test_list_json_missing_or_malformed_owner_is_null(
        self, mock_authenticated_client: MagicMock, owned_by: object
    ) -> None:
        raw_account: dict = {"id": "acc_123", "displayName": "Chase Checking"}
        raw_account["ownedByUser"] = owned_by
        response = {"accounts": [raw_account]}

        async def async_accounts() -> dict:
            return response

        mock_authenticated_client.get_accounts = async_accounts
        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload[0]["owner_id"] in (None, "user-1")
        assert payload[0]["owner_name"] in (None, "Alex")
        assert "is_shared" not in payload[0]
        assert "owner_id" in payload[0]
        assert "owner_name" in payload[0]

    def test_list_quiet_remains_id_only(self, mock_authenticated_client: MagicMock) -> None:
        response = {
            "accounts": [
                {
                    "id": "acc_123",
                    "displayName": "Chase Checking",
                    "ownedByUser": {"id": "user-1", "displayName": "Alex"},
                }
            ]
        }

        async def async_accounts() -> dict:
            return response

        mock_authenticated_client.get_accounts = async_accounts
        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
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
        assert result.stdout.strip() == "acc_123"

    def test_list_raw_keeps_owner_structure_untouched(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        owned = {"id": "user-1", "displayName": "Alex", "profilePictureUrl": "https://x"}
        response = {"accounts": [{"id": "acc_123", "ownedByUser": owned}]}

        async def async_accounts() -> dict:
            return response

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
        payload = json.loads(result.stdout)
        assert payload["accounts"][0]["ownedByUser"] == owned


class TestAccountsListLiability:
    """Liability and debt-service metadata in account list output.

    Normalized output carries the direct ``is_asset`` classification, stable
    ``type_name``/``subtype_name`` identifiers, and the distinct nullable
    liability fields. Concise formats (plain/table/compact) stay small;
    JSON/CSV keep everything; raw is untouched; quiet stays ID-only.
    """

    CREDIT_RAW = {
        "id": "acc_credit",
        "displayName": "Shared Visa",
        "type": {"name": "liability", "display": "Credit Card"},
        "subtype": {"name": "credit_card", "display": "Credit Card"},
        "currentBalance": -1250.5,
        "isHidden": False,
        "isManual": False,
        "isAsset": False,
        "limit": 5000.0,
        "dataProviderCreditLimit": 5100.0,
        "apr": 0.2499,
        "interestRate": 24.99,
        "minimumPayment": 25.0,
        "plannedPayment": 50.0,
        "excludeFromDebtPaydown": False,
    }

    def _invoke_list(
        self, mock_authenticated_client: MagicMock, accounts: list[dict], args: list[str]
    ):
        response = {"accounts": accounts}

        async def async_accounts() -> dict:
            return response

        mock_authenticated_client.get_accounts = async_accounts
        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
                return_value=mock_authenticated_client,
            ),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            return runner.invoke(app, args)

    def test_list_json_credit_card_liability_metadata(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        result = self._invoke_list(mock_authenticated_client, [self.CREDIT_RAW], ["list", "--json"])
        assert result.exit_code == 0
        record = json.loads(result.stdout)[0]
        assert record["is_asset"] is False
        assert record["type_name"] == "liability"
        assert record["subtype_name"] == "credit_card"
        assert record["credit_limit"] == 5000.0
        assert record["provider_credit_limit"] == 5100.0
        assert record["apr"] == 0.2499
        assert record["interest_rate"] == 24.99
        assert record["minimum_payment"] == 25.0
        assert record["planned_payment"] == 50.0
        assert record["excluded_from_debt_paydown"] is False
        assert record["credit_limit"] != record["provider_credit_limit"]

    def test_list_json_null_partial_zero_negative_stay_distinguishable(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        result = self._invoke_list(
            mock_authenticated_client,
            [
                {"id": "acc_partial", "isAsset": None, "limit": 0, "minimumPayment": -1.5},
                {"id": "acc_bare"},
            ],
            ["list", "--json"],
        )
        assert result.exit_code == 0
        records = json.loads(result.stdout)
        assert records[0]["is_asset"] is None
        assert records[0]["credit_limit"] == 0
        assert records[0]["minimum_payment"] == -1.5
        assert records[0]["apr"] is None
        for record in records:
            for field in (
                "provider_credit_limit",
                "planned_payment",
                "excluded_from_debt_paydown",
                "type_name",
                "subtype_name",
            ):
                assert record[field] is None

    def test_list_plain_shows_asset_liability_classification(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        result = self._invoke_list(
            mock_authenticated_client, [self.CREDIT_RAW], ["list", "--format", "plain"]
        )
        assert result.exit_code == 0
        # Plain human formatting renders the classification and the small
        # liability subset (Yes/No booleans, locale-formatted numbers).
        assert "Is Asset: No" in result.stdout
        assert "Credit Limit: 5,000.00" in result.stdout
        assert "Apr: 0.25" in result.stdout

    def test_list_compact_is_concise_and_json_complete(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        compact = self._invoke_list(
            mock_authenticated_client, [self.CREDIT_RAW], ["list", "--format", "compact"]
        )
        assert compact.exit_code == 0
        compact_record = json.loads(compact.stdout)[0]
        assert set(compact_record) == set(ACCOUNT_LIST_DISPLAY_FIELDS)

        full = self._invoke_list(mock_authenticated_client, [self.CREDIT_RAW], ["list", "--json"])
        full_record = json.loads(full.stdout)[0]
        for field in (
            "provider_credit_limit",
            "interest_rate",
            "minimum_payment",
            "planned_payment",
            "excluded_from_debt_paydown",
        ):
            assert field in full_record

    def test_list_csv_keeps_all_liability_fields(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        result = self._invoke_list(
            mock_authenticated_client, [self.CREDIT_RAW], ["list", "--format", "csv"]
        )
        assert result.exit_code == 0
        header = result.stdout.splitlines()[0]
        for field in (
            "credit_limit",
            "provider_credit_limit",
            "apr",
            "interest_rate",
            "minimum_payment",
            "planned_payment",
            "excluded_from_debt_paydown",
            "type_name",
            "subtype_name",
            "is_asset",
        ):
            assert field in header

    def test_list_quiet_remains_id_only_with_liability_payload(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        response = {"accounts": [self.CREDIT_RAW]}

        async def async_accounts() -> dict:
            return response

        mock_authenticated_client.get_accounts = async_accounts
        with (
            patch(
                "monarch_cli.services.accounts.get_authenticated_client",
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
        assert result.stdout.strip() == "acc_credit"

    def test_list_raw_preserves_liability_fields_verbatim(
        self, mock_authenticated_client: MagicMock
    ) -> None:
        response = {"accounts": [self.CREDIT_RAW]}

        async def async_accounts() -> dict:
            return response

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
        record = json.loads(result.stdout)["accounts"][0]
        assert record["isAsset"] is False
        assert record["dataProviderCreditLimit"] == 5100.0
        assert record["excludeFromDebtPaydown"] is False
        assert "is_asset" not in record


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


class TestAccountHistoryAndSnapshotsCommands:
    """CLI contract tests for the read-only account history surface."""

    def test_history_json(self) -> None:
        with (
            patch(
                "monarch_cli.commands.accounts.get_account_history",
                return_value=[{"date": "2024-01-01", "balance": None}],
            ) as mock_history,
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["history", "opaque-id", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)[0]["balance"] is None
        mock_history.assert_called_once_with("opaque-id", raw=False)

    def test_recent_balances_has_no_end_option(self) -> None:
        result = runner.invoke(app, ["recent-balances", "--help"])
        assert result.exit_code == 0
        plain = result.stdout.replace("\x1b[1m", "").replace("\x1b[0m", "")
        assert "start" in plain
        assert "end-date filter" in plain
        assert "--end" not in plain

    def test_snapshots_by_type_preserves_month_precision(self) -> None:
        payload = {
            "snapshots": [{"account_type": "asset", "period": "2024-01", "balance": 1}],
            "account_types": [],
        }
        with (
            patch(
                "monarch_cli.commands.accounts.get_account_snapshots_by_type",
                return_value=payload,
            ) as mock_snapshots,
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                ["snapshots-by-type", "--start", "2024-01-01", "--timeframe", "month", "--json"],
            )
        assert result.exit_code == 0
        assert json.loads(result.stdout)["snapshots"][0]["period"] == "2024-01"
        mock_snapshots.assert_called_once_with("2024-01-01", "month", raw=False)

    def test_refresh_status_unknown_ids_are_explicit(self) -> None:
        payload = {
            "status": "unknown",
            "complete": None,
            "requested_account_ids": ["missing"],
            "known_account_ids": [],
            "unknown_account_ids": ["missing"],
            "checked_account_count": 0,
        }
        with (
            patch("monarch_cli.commands.accounts.get_refresh_status", return_value=payload),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(app, ["refresh-status", "-a", "missing", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)["status"] == "unknown"


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
