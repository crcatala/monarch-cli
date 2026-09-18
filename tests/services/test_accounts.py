"""Unit tests for account service layer.

⚠️ NOTE: refresh_accounts() must NOT be tested against the live API.
Use mocks to verify logic without executing actual refresh requests.
"""

from unittest.mock import MagicMock, patch

import pytest

from monarch_cli.core.exceptions import APIError, MutationAmbiguousError, ValidationError
from monarch_cli.core.operations import (
    Effect,
    Operation,
    reset_mutation_authorization,
    set_mutation_authorized,
)
from monarch_cli.services.accounts import (
    get_account_history,
    get_account_ids,
    get_account_snapshots_by_type,
    get_account_type_options,
    get_aggregate_snapshots,
    get_recent_account_balances,
    get_refresh_status,
    list_account_types,
    list_accounts,
    refresh_accounts,
)

READ_OPERATION = Operation("accounts list", frozenset({Effect.READ_ONLY}))
TYPES_OPERATION = Operation("accounts types", frozenset({Effect.READ_ONLY}))
MUTATION_OPERATION = Operation("accounts refresh", frozenset({Effect.REMOTE_MUTATION}))


@pytest.fixture(autouse=True)
def authorize_mutation_service_tests():
    set_mutation_authorized(True)
    yield
    reset_mutation_authorization()


# Sample raw API response
SAMPLE_RAW_RESPONSE = {
    "accounts": [
        {
            "id": "acc-123",
            "displayName": "Primary Checking",
            "type": {"display": "Checking"},
            "subtype": {"display": "Personal"},
            "currentBalance": 1234.56,
            "institution": {"name": "Big Bank"},
            "isHidden": False,
            "isManual": False,
            "updatedAt": "2024-01-15T10:30:00Z",
        },
        {
            "id": "acc-456",
            "displayName": "Savings",
            "type": {"display": "Savings"},
            "currentBalance": 5000.00,
            "institution": {"name": "Big Bank"},
            "isHidden": False,
            "isManual": False,
        },
    ]
}

EMPTY_RAW_RESPONSE = {"accounts": []}


class TestListAccounts:
    """Tests for list_accounts function."""

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_returns_transformed_accounts(self, mock_run_async, _mock_get_client):
        """Should return transformed accounts from raw API response."""
        mock_run_async.return_value = SAMPLE_RAW_RESPONSE

        result = list_accounts()

        assert len(result) == 2
        assert result[0]["id"] == "acc-123"
        assert result[0]["name"] == "Primary Checking"
        assert result[0]["type"] == "Checking"
        assert result[1]["id"] == "acc-456"

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_uses_authenticated_client(self, mock_run_async, mock_get_client):
        """Should get authenticated client and call get_accounts."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = EMPTY_RAW_RESPONSE

        list_accounts()

        mock_get_client.assert_called_once()
        mock_run_async.assert_called_once()

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_handles_empty_accounts(self, mock_run_async, _mock_get_client):
        """Should return empty list when no accounts."""
        mock_run_async.return_value = EMPTY_RAW_RESPONSE

        result = list_accounts()

        assert result == []


SAMPLE_TYPE_OPTIONS_RAW = {
    "accountTypeOptions": [
        {
            "type": {
                "name": "asset",
                "display": "Asset",
                "group": "assets",
                "possibleSubtypes": [
                    {"name": "checking", "display": "Checking"},
                ],
            },
            "subtype": None,
        },
    ]
}


class TestGetAccountTypeOptions:
    """Tests for the raw account type-discovery accessor."""

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_returns_raw_response_untouched(self, mock_run_async, _mock_get_client):
        """Should return the upstream response without normalization."""
        mock_run_async.return_value = SAMPLE_TYPE_OPTIONS_RAW

        result = get_account_type_options()

        assert result == SAMPLE_TYPE_OPTIONS_RAW

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_calls_client_get_account_type_options(self, mock_run_async, mock_get_client):
        """Should use the authenticated client's get_account_type_options."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = SAMPLE_TYPE_OPTIONS_RAW

        get_account_type_options()

        mock_get_client.assert_called_once()
        # The read executor receives a factory that invokes the upstream method.
        coro_factory = mock_run_async.call_args[0][0]
        coro_factory()
        mock_client.get_account_type_options.assert_called_once_with()

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_accepts_explicit_operation(self, mock_run_async, _mock_get_client):
        """The operation descriptor is forwarded to the read executor."""
        mock_run_async.return_value = SAMPLE_TYPE_OPTIONS_RAW

        get_account_type_options(operation=TYPES_OPERATION)

        assert mock_run_async.call_args[0][1] == TYPES_OPERATION


class TestListAccountTypes:
    """Tests for list_account_types normalization orchestration."""

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_returns_normalized_type_records(self, mock_run_async, _mock_get_client):
        """Should flatten the raw hierarchy into normalized records."""
        mock_run_async.return_value = SAMPLE_TYPE_OPTIONS_RAW

        result = list_account_types()

        assert result == [
            {
                "group": "assets",
                "type": "asset",
                "type_display": "Asset",
                "subtype": "checking",
                "subtype_display": "Checking",
            }
        ]

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_handles_empty_options(self, mock_run_async, _mock_get_client):
        """Should return an empty list when no options exist."""
        mock_run_async.return_value = {"accountTypeOptions": []}

        assert list_account_types() == []

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_uses_read_only_operation_descriptor(self, mock_run_async, _mock_get_client):
        """The default operation descriptor is read-only."""
        mock_run_async.return_value = SAMPLE_TYPE_OPTIONS_RAW

        list_account_types()

        operation = mock_run_async.call_args[0][1]
        assert Effect.READ_ONLY in operation.effects
        assert Effect.REMOTE_MUTATION not in operation.effects

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_propagates_malformed_root_error(self, mock_run_async, _mock_get_client):
        """A non-object upstream payload surfaces the typed transformer error."""
        mock_run_async.return_value = ["not", "an", "object"]

        with pytest.raises(APIError):
            list_account_types()


class TestGetAccountIds:
    """Tests for get_account_ids function."""

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_returns_id_strings(self, mock_run_async, _mock_get_client):
        """Should return list of account ID strings."""
        mock_run_async.return_value = SAMPLE_RAW_RESPONSE

        result = get_account_ids()

        assert result == ["acc-123", "acc-456"]
        assert all(isinstance(id_, str) for id_ in result)

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_handles_empty_accounts(self, mock_run_async, _mock_get_client):
        """Should return empty list when no accounts."""
        mock_run_async.return_value = EMPTY_RAW_RESPONSE

        result = get_account_ids()

        assert result == []

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_filters_none_ids(self, mock_run_async, _mock_get_client):
        """Should not include accounts with None IDs."""
        mock_run_async.return_value = {
            "accounts": [
                {"id": "acc-123", "displayName": "Valid"},
                {"displayName": "No ID"},  # Missing ID
            ]
        }

        result = get_account_ids()

        assert result == ["acc-123"]


class TestRefreshAccounts:
    """Tests for refresh_accounts function.

    ⚠️ CRITICAL: These tests use mocks to avoid hitting the live API.
    Never call refresh_accounts() against real Monarch credentials in tests.
    """

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_refreshes_provided_account_ids(self, mock_run_async, mock_get_client):
        """Should refresh only the provided account IDs."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = True  # request_accounts_refresh returns bool

        result = refresh_accounts(account_ids=["acc-123", "acc-456"], operation=MUTATION_OPERATION)

        assert result["schema_version"] == "mutation-outcome.v1"
        assert result["operation"] == "accounts.refresh"
        assert result["status"] == "succeeded"
        assert result["summary"] == {
            "total": 2,
            "succeeded": 2,
            "failed": 0,
            "ambiguous": 0,
        }
        assert [item["id"] for item in result["items"]] == ["acc-123", "acc-456"]
        assert all(item["status"] == "succeeded" for item in result["items"])
        assert result["verification"] is None

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    @patch("monarch_cli.services.accounts.get_account_ids")
    def test_fetches_all_ids_when_none_provided(
        self, mock_get_ids, mock_run_async, mock_get_client
    ):
        """Should fetch all account IDs when none provided."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_get_ids.return_value = ["acc-123", "acc-456", "acc-789"]
        mock_run_async.return_value = True

        result = refresh_accounts(account_ids=None, operation=MUTATION_OPERATION)

        mock_get_ids.assert_called_once()
        assert result["status"] == "succeeded"
        assert result["summary"]["total"] == 3
        assert [item["id"] for item in result["items"]] == ["acc-123", "acc-456", "acc-789"]

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    @patch("monarch_cli.services.accounts.get_account_ids")
    def test_returns_no_accounts_status(self, mock_get_ids, _mock_run_async, _mock_get_client):
        """Should return no_accounts status when no accounts found."""
        mock_get_ids.return_value = []

        result = refresh_accounts(account_ids=None, operation=MUTATION_OPERATION)

        assert result["status"] == "no_accounts"
        assert result["account_count"] == 0
        assert "No accounts found" in result["message"]

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_returns_no_accounts_for_empty_list(self, _mock_run_async, _mock_get_client):
        """Should return no_accounts status when empty list provided."""
        result = refresh_accounts(account_ids=[], operation=MUTATION_OPERATION)

        assert result["status"] == "no_accounts"
        assert result["account_count"] == 0

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_returns_failed_status_on_refresh_failure(self, mock_run_async, mock_get_client):
        """Should return failed status when refresh request fails."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = False  # Refresh failed

        result = refresh_accounts(account_ids=["acc-123"], operation=MUTATION_OPERATION)

        assert result["status"] == "failed"
        assert result["summary"] == {
            "total": 1,
            "succeeded": 0,
            "failed": 1,
            "ambiguous": 0,
        }
        (item,) = result["items"]
        assert item["entity"] == "account"
        assert item["id"] == "acc-123"
        assert item["status"] == "failed"
        assert item["result"] is None
        assert item["error"]["code"] == "API_ERROR"
        assert result["verification"] is None

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_definite_rejection_returns_failed_envelope(self, mock_run_async, mock_get_client):
        """A definite post-attempt API rejection is a failed envelope, not a stderr error.

        Upstream ``request_accounts_refresh`` reports rejection by raising,
        never by returning a falsy value, so the raised structured error must
        become a failed mutation-outcome.v1 envelope (mc-ik8o).
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.side_effect = APIError("refresh rejected", status_code=422)

        result = refresh_accounts(account_ids=["acc-123"], operation=MUTATION_OPERATION)

        assert result["schema_version"] == "mutation-outcome.v1"
        assert result["operation"] == "accounts.refresh"
        assert result["status"] == "failed"
        assert result["summary"] == {
            "total": 1,
            "succeeded": 0,
            "failed": 1,
            "ambiguous": 0,
        }
        (item,) = result["items"]
        assert item["entity"] == "account"
        assert item["id"] == "acc-123"
        assert item["status"] == "failed"
        assert item["result"] is None
        assert item["error"] == {
            "code": "API_ERROR",
            "message": "refresh rejected",
            "details": {"status_code": 422},
        }
        # A definitive failure needs no follow-up verification.
        assert result["verification"] is None

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_arbitrary_rejection_exception_is_sanitized(self, mock_run_async, mock_get_client):
        """Arbitrary upstream exception text never reaches the envelope."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        secret = "raw graphql variables and password=hunter2"
        mock_run_async.side_effect = RuntimeError(secret)

        result = refresh_accounts(account_ids=["acc-123"], operation=MUTATION_OPERATION)

        assert result["status"] == "failed"
        (item,) = result["items"]
        assert item["error"]["code"] == "UNKNOWN"
        assert secret not in item["error"]["message"]
        assert item["error"]["details"] == {"exception_class": "RuntimeError"}

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_ambiguous_refresh_propagates_with_entity_ids(
        self, mock_run_mutation, _mock_get_client
    ):
        """Refresh reports an ambiguous envelope, never an ordinary failure."""
        mock_run_mutation.side_effect = MutationAmbiguousError(
            details={"operation": "accounts refresh", "entity_ids": ["acc-123"]}
        )

        result = refresh_accounts(account_ids=["acc-123"], operation=MUTATION_OPERATION)

        assert mock_run_mutation.call_args.kwargs["entity_ids"] == ("acc-123",)
        assert "verify" in mock_run_mutation.call_args.kwargs["verification"].lower()
        assert result["schema_version"] == "mutation-outcome.v1"
        assert result["status"] == "ambiguous"
        (item,) = result["items"]
        assert item["entity"] == "account"
        assert item["id"] == "acc-123"
        assert item["status"] == "ambiguous"
        assert item["error"]["code"] == "MUTATION_AMBIGUOUS"
        assert item["error"]["details"]["remote_state"] == "unknown"
        # Ambiguity requires recovery guidance. No observational refresh-status
        # read command exists yet, so no verification command is tokenized.
        assert result["verification"]["required"] is True
        assert "verify" in result["verification"]["message"].lower()
        assert result["verification"]["command"] is None

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_mutation_call")
    def test_result_has_required_keys(self, mock_run_async, _mock_get_client):
        """Result dict must have status, account_count, and message."""
        mock_run_async.return_value = True

        result = refresh_accounts(account_ids=["acc-123"], operation=MUTATION_OPERATION)

        # The mutation-outcome.v1 envelope always carries every required
        # top-level field.
        assert result["schema_version"] == "mutation-outcome.v1"
        assert result["operation"] == "accounts.refresh"
        assert "status" in result
        assert "summary" in result
        assert "items" in result
        assert "verification" in result


class TestAccountHistoryAndSnapshots:
    """Unit tests for read-only account history and snapshot services."""

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_history_passes_opaque_id_without_numeric_coercion(
        self, mock_run_read, mock_get_client
    ):
        mock_run_read.return_value = [{"date": "2024-01-01", "signedBalance": None}]
        result = get_account_history("opaque-001")
        assert result[0]["account_id"] is None
        factory = mock_run_read.call_args.args[0]
        factory()
        mock_get_client.return_value.get_account_history.assert_called_once_with("opaque-001")

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_recent_balances_maps_start_only(self, mock_run_read, mock_get_client):
        mock_run_read.return_value = {"accounts": []}
        assert get_recent_account_balances("2024-01-01") == []
        factory = mock_run_read.call_args.args[0]
        factory()
        mock_get_client.return_value.get_recent_account_balances.assert_called_once_with(
            "2024-01-01"
        )

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_aggregate_passes_parsed_date_objects(self, mock_run_read, mock_get_client):
        mock_run_read.return_value = {"aggregateSnapshots": []}
        assert get_aggregate_snapshots("2024-01-01", "2024-01-31") == []
        factory = mock_run_read.call_args.args[0]
        factory()
        from datetime import date

        mock_get_client.return_value.get_aggregate_snapshots.assert_called_once_with(
            start_date=date(2024, 1, 1), end_date=date(2024, 1, 31), account_type=None
        )

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_type_snapshots_preserve_upstream_period(self, mock_run_read, mock_get_client):
        mock_run_read.return_value = {
            "snapshotsByAccountType": [{"accountType": "asset", "month": "2024-01", "balance": 1}],
            "accountTypes": [],
        }
        result = get_account_snapshots_by_type("2024-01-01", "month")
        assert result["snapshots"][0]["period"] == "2024-01"
        factory = mock_run_read.call_args.args[0]
        factory()
        mock_get_client.return_value.get_account_snapshots_by_type.assert_called_once_with(
            "2024-01-01", "month"
        )

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_invalid_dates_and_timeframe_fail_before_client_call(
        self, mock_run_read, mock_get_client
    ):
        with pytest.raises(ValidationError):
            get_recent_account_balances("2024-02-30")
        with pytest.raises(ValidationError):
            get_aggregate_snapshots("2024-02-01", "2024-01-01")
        with pytest.raises(ValidationError):
            get_account_snapshots_by_type("2024-01-01", "quarter")
        mock_get_client.assert_not_called()
        mock_run_read.assert_not_called()

    @patch("monarch_cli.services.accounts.list_account_types")
    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_unknown_type_filter_fails_before_snapshot_call(
        self, mock_run_read, _mock_get_client, mock_list_types
    ):
        mock_list_types.return_value = [{"type": "asset"}]
        with pytest.raises(ValidationError):
            get_aggregate_snapshots("2024-01-01", "2024-01-31", account_type="liability")
        mock_run_read.assert_not_called()

    @patch("monarch_cli.services.accounts.list_accounts")
    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_read_call")
    def test_unknown_refresh_ids_return_unknown_without_status_call(
        self, mock_run_read, mock_get_client, mock_list_accounts
    ):
        mock_list_accounts.return_value = [{"id": "known"}]
        result = get_refresh_status(["known", "unknown"])
        assert result["status"] == "unknown"
        assert result["unknown_account_ids"] == ["unknown"]
        mock_run_read.assert_not_called()
        mock_get_client.assert_not_called()
