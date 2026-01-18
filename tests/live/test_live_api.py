"""Live API tests - LOCAL DEVELOPMENT ONLY.

⚠️ WARNING: These tests hit the real Monarch Money API!
⚠️ They require valid credentials and are NOT for CI.

These tests verify that:
1. Authentication works with real credentials
2. The CLI can communicate with the Monarch Money API
3. Response structures match our expectations

To run:
    MONARCH_LIVE_TESTS=1 make test-live

Prerequisites:
    - Valid Monarch Money credentials stored via `monarch auth login`
    - Active internet connection
    - Session not expired
"""

import os

import pytest

# Skip all tests in this module unless MONARCH_LIVE_TESTS=1
LIVE_ENABLED = os.environ.get("MONARCH_LIVE_TESTS", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_ENABLED, reason="Live tests disabled (set MONARCH_LIVE_TESTS=1)"),
]


@pytest.fixture
def live_client():
    """Create a real MonarchMoney client with stored credentials.

    LOCAL DEV ONLY: This uses your real Monarch Money session.
    """
    from monarch_cli.core.session import get_session_token

    token = get_session_token()
    if not token:
        pytest.skip("No active session - run 'monarch auth login' first")

    from monarchmoney import MonarchMoney

    client = MonarchMoney()
    client.set_token(token)
    return client


class TestLiveAccounts:
    """Live tests for account fetching.

    LOCAL DEV ONLY: Hits real Monarch Money API.
    """

    @pytest.mark.asyncio
    async def test_can_fetch_accounts(self, live_client):
        """Verify we can fetch accounts from the real API.

        LOCAL DEV ONLY: This test verifies authentication works and
        the API returns expected structure. It does NOT assert on
        specific account names or balances (those are user data).
        """
        accounts_data = await live_client.get_accounts()

        # Verify structure, not specific values
        assert "accounts" in accounts_data
        assert isinstance(accounts_data["accounts"], list)

        # If user has accounts, verify structure of first one
        if accounts_data["accounts"]:
            account = accounts_data["accounts"][0]
            # These fields should always exist
            assert "id" in account
            assert "displayName" in account
            assert "currentBalance" in account

    @pytest.mark.asyncio
    async def test_accounts_have_required_fields(self, live_client):
        """Verify account responses have all fields we depend on.

        LOCAL DEV ONLY: Validates API contract hasn't changed.
        """
        accounts_data = await live_client.get_accounts()

        if not accounts_data["accounts"]:
            pytest.skip("No accounts in this Monarch account")

        account = accounts_data["accounts"][0]

        # Fields required for our transformers
        required_fields = ["id", "displayName", "currentBalance", "type", "isHidden"]

        for field in required_fields:
            assert field in account, f"Required field '{field}' missing from account response"


class TestLiveTransactions:
    """Live tests for transaction fetching.

    LOCAL DEV ONLY: Hits real Monarch Money API.
    """

    @pytest.mark.asyncio
    async def test_can_fetch_transactions(self, live_client):
        """Verify we can fetch transactions from the real API.

        LOCAL DEV ONLY: This test verifies the API returns expected
        structure. It does NOT assert on transaction amounts or
        descriptions (those are user data).
        """
        txns_data = await live_client.get_transactions(limit=5)

        # Verify structure
        assert "allTransactions" in txns_data
        assert "results" in txns_data["allTransactions"]
        assert isinstance(txns_data["allTransactions"]["results"], list)

    @pytest.mark.asyncio
    async def test_transactions_have_required_fields(self, live_client):
        """Verify transaction responses have all fields we depend on.

        LOCAL DEV ONLY: Validates API contract hasn't changed.
        """
        txns_data = await live_client.get_transactions(limit=1)

        results = txns_data["allTransactions"]["results"]
        if not results:
            pytest.skip("No transactions in this Monarch account")

        txn = results[0]

        # Fields required for our transformers
        required_fields = ["id", "date", "amount", "merchant", "category"]

        for field in required_fields:
            assert field in txn, f"Required field '{field}' missing from transaction response"


class TestLiveAuth:
    """Live tests for authentication.

    LOCAL DEV ONLY: Verifies session is valid.
    """

    @pytest.mark.asyncio
    async def test_session_is_valid(self, live_client):
        """Verify the stored session token is still valid.

        LOCAL DEV ONLY: This is a simple API call to verify auth works.
        If this fails, run 'monarch auth login' to refresh credentials.
        """
        # get_subscription is a lightweight call that requires auth
        try:
            result = await live_client.get_subscription_details()
            assert result is not None
        except Exception as e:
            pytest.fail(f"Session appears invalid: {e}. Run 'monarch auth login' to refresh.")
