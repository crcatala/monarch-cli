"""Unit tests for account service layer.

⚠️ NOTE: refresh_accounts() must NOT be tested against the live API.
Use mocks to verify logic without executing actual refresh requests.
"""

from unittest.mock import MagicMock, patch

from monarch_cli.services.accounts import (
    get_account_ids,
    list_accounts,
    refresh_accounts,
)

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
    @patch("monarch_cli.services.accounts.run_api_call")
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
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_uses_authenticated_client(self, mock_run_async, mock_get_client):
        """Should get authenticated client and call get_accounts."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = EMPTY_RAW_RESPONSE

        list_accounts()

        mock_get_client.assert_called_once()
        mock_run_async.assert_called_once()

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_handles_empty_accounts(self, mock_run_async, _mock_get_client):
        """Should return empty list when no accounts."""
        mock_run_async.return_value = EMPTY_RAW_RESPONSE

        result = list_accounts()

        assert result == []


class TestGetAccountIds:
    """Tests for get_account_ids function."""

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_returns_id_strings(self, mock_run_async, _mock_get_client):
        """Should return list of account ID strings."""
        mock_run_async.return_value = SAMPLE_RAW_RESPONSE

        result = get_account_ids()

        assert result == ["acc-123", "acc-456"]
        assert all(isinstance(id_, str) for id_ in result)

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_handles_empty_accounts(self, mock_run_async, _mock_get_client):
        """Should return empty list when no accounts."""
        mock_run_async.return_value = EMPTY_RAW_RESPONSE

        result = get_account_ids()

        assert result == []

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
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
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_refreshes_provided_account_ids(self, mock_run_async, mock_get_client):
        """Should refresh only the provided account IDs."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = True  # request_accounts_refresh returns bool

        result = refresh_accounts(account_ids=["acc-123", "acc-456"])

        assert result["status"] == "ok"
        assert result["account_count"] == 2
        assert "2 account(s)" in result["message"]

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    @patch("monarch_cli.services.accounts.get_account_ids")
    def test_fetches_all_ids_when_none_provided(
        self, mock_get_ids, mock_run_async, mock_get_client
    ):
        """Should fetch all account IDs when none provided."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_get_ids.return_value = ["acc-123", "acc-456", "acc-789"]
        mock_run_async.return_value = True

        result = refresh_accounts(account_ids=None)

        mock_get_ids.assert_called_once()
        assert result["status"] == "ok"
        assert result["account_count"] == 3

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    @patch("monarch_cli.services.accounts.get_account_ids")
    def test_returns_no_accounts_status(self, mock_get_ids, _mock_run_async, _mock_get_client):
        """Should return no_accounts status when no accounts found."""
        mock_get_ids.return_value = []

        result = refresh_accounts(account_ids=None)

        assert result["status"] == "no_accounts"
        assert result["account_count"] == 0
        assert "No accounts found" in result["message"]

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_returns_no_accounts_for_empty_list(self, _mock_run_async, _mock_get_client):
        """Should return no_accounts status when empty list provided."""
        result = refresh_accounts(account_ids=[])

        assert result["status"] == "no_accounts"
        assert result["account_count"] == 0

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_returns_failed_status_on_refresh_failure(self, mock_run_async, mock_get_client):
        """Should return failed status when refresh request fails."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_run_async.return_value = False  # Refresh failed

        result = refresh_accounts(account_ids=["acc-123"])

        assert result["status"] == "failed"
        assert result["account_count"] == 1
        assert "failed" in result["message"].lower()

    @patch("monarch_cli.services.accounts.get_authenticated_client")
    @patch("monarch_cli.services.accounts.run_api_call")
    def test_result_has_required_keys(self, mock_run_async, _mock_get_client):
        """Result dict must have status, account_count, and message."""
        mock_run_async.return_value = True

        result = refresh_accounts(account_ids=["acc-123"])

        assert "status" in result
        assert "account_count" in result
        assert "message" in result
