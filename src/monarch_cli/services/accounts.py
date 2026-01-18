"""Account service layer - orchestrates account operations.

Service layer is used for operations requiring multi-step orchestration,
like refresh which needs to fetch account IDs first if not provided.
"""

from __future__ import annotations

from typing import Any

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..transformers.accounts import transform_accounts


def list_accounts() -> list[dict[str, Any]]:
    """Fetch and transform all accounts.

    Returns:
        List of transformed account dicts with stable field names.

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
    """
    client = get_authenticated_client()
    raw = run_async(client.get_accounts())
    return transform_accounts(raw)


def get_account_ids() -> list[str]:
    """Get list of all account IDs.

    Returns:
        List of account ID strings.

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
    """
    accounts = list_accounts()
    return [acc["id"] for acc in accounts if acc.get("id")]


def refresh_accounts(account_ids: list[str] | None = None) -> dict[str, Any]:
    """Request accounts refresh from linked institutions.

    If no account IDs provided, refreshes all accounts.

    Args:
        account_ids: Optional list of specific account IDs to refresh.
                    If None, fetches and refreshes all accounts.

    Returns:
        Dict with:
            - status: 'ok', 'no_accounts', or 'failed'
            - account_count: Number of accounts refreshed
            - message: Human-readable status message

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
    """
    client = get_authenticated_client()

    # Fetch all account IDs if none provided
    if account_ids is None:
        account_ids = get_account_ids()

    # Handle case where no accounts exist
    if not account_ids:
        return {
            "status": "no_accounts",
            "account_count": 0,
            "message": "No accounts found to refresh",
        }

    # Request refresh
    success = run_async(client.request_accounts_refresh(account_ids))

    if success:
        return {
            "status": "ok",
            "account_count": len(account_ids),
            "message": f"Refresh requested for {len(account_ids)} account(s)",
        }
    else:
        return {
            "status": "failed",
            "account_count": len(account_ids),
            "message": "Refresh request failed",
        }
