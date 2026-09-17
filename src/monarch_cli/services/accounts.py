"""Account service layer - orchestrates account operations.

Service layer is used for operations requiring multi-step orchestration,
like refresh which needs to fetch account IDs first if not provided.

Every API interaction goes through the shared remote-operation boundary with
an explicit :class:`Operation` descriptor, so account refresh (a remote
mutation) can never execute without per-invocation authorization or through
the read executor.
"""

from __future__ import annotations

from typing import Any

from ..core.adapter import get_authenticated_client
from ..core.operations import (
    Effect,
    Operation,
    PolicyViolationError,
    require_mutation_authorization,
    run_mutation_call,
    run_read_call,
)
from ..transformers.accounts import transform_accounts

#: Descriptor for the read-only account listing operation.
LIST_ACCOUNTS_OPERATION = Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY}))


def list_accounts(
    operation: Operation = LIST_ACCOUNTS_OPERATION,
) -> list[dict[str, Any]]:
    """Fetch and transform all accounts.

    Args:
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        List of transformed account dicts with stable field names.

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
        NetworkError: On timeout or network failure.
    """
    client = get_authenticated_client()
    raw = run_read_call(lambda: client.get_accounts(), operation)
    return transform_accounts(raw)


def get_account_ids(
    operation: Operation = LIST_ACCOUNTS_OPERATION,
) -> list[str]:
    """Get list of all account IDs.

    Args:
        operation: Explicit descriptor for the invoking operation.

    Returns:
        List of account ID strings.

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
        NetworkError: On timeout or network failure.
    """
    accounts = list_accounts(operation)
    return [acc["id"] for acc in accounts if acc.get("id")]


def refresh_accounts(
    account_ids: list[str] | None = None,
    operation: Operation | None = None,
) -> dict[str, Any]:
    """Request accounts refresh from linked institutions.

    If no account IDs provided, refreshes all accounts.

    Args:
        account_ids: Optional list of specific account IDs to refresh.
                    If None, fetches and refreshes all accounts.
        operation: Explicit descriptor for the refresh invocation. Required
                    to carry the ``remote_mutation`` effect.

    Returns:
        Dict with:
            - status: 'ok', 'no_accounts', or 'failed'
            - account_count: Number of accounts refreshed
            - message: Human-readable status message

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
        NetworkError: On timeout or network failure.
        PolicyViolationError: If the descriptor lacks the remote_mutation
            effect (metadata/execution disagreement).
        MutationBlockedError: If the invocation lacks --allow-mutations.
    """
    if operation is None or Effect.REMOTE_MUTATION not in operation.effects:
        raise PolicyViolationError(
            "refresh_accounts requires an Operation descriptor with the remote_mutation effect."
        )
    # Block direct service callers before even the read-only account discovery
    # needed to resolve an omitted account list.
    require_mutation_authorization(operation)

    # Fetch all account IDs through the read descriptor before entering the
    # mutation call. The discovery query is observational even when the
    # surrounding refresh invocation is a remote mutation.
    if account_ids is None:
        account_ids = get_account_ids()

    # Handle case where no accounts exist
    if not account_ids:
        return {
            "status": "no_accounts",
            "account_count": 0,
            "message": "No accounts found to refresh",
        }

    # Request refresh (through the shared mutation boundary). Resolve the
    # authenticated client inside the callable so the boundary remains before
    # client creation for direct service callers as well as CLI callers.
    # The refresh is a single attempt: on timeout/disconnect the outcome is
    # reported as MUTATION_AMBIGUOUS (exit 4) rather than a plain failure,
    # with verification guidance for the affected account IDs.
    success = run_mutation_call(
        lambda: get_authenticated_client().request_accounts_refresh(account_ids),
        operation,
        entity_ids=tuple(account_ids),
        verification=(
            "Verify the refresh status for the listed account(s) in the Monarch "
            "web UI (Accounts page) before requesting another refresh; a "
            "pending institution sync may still be in progress."
        ),
    )

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
