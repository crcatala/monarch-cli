"""Account service layer - orchestrates account operations.

Service layer is used for operations requiring multi-step orchestration,
like refresh which needs to fetch account IDs first if not provided.

Every API interaction goes through the shared remote-operation boundary with
an explicit :class:`Operation` descriptor, so account refresh (a remote
mutation) can never execute without per-invocation authorization or through
the read executor.
"""

from __future__ import annotations

from typing import Any, cast

from ..core.adapter import get_authenticated_client
from ..core.exceptions import MutationAmbiguousError
from ..core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    succeeded_item,
    verification_object,
)
from ..core.operations import (
    Effect,
    Operation,
    PolicyViolationError,
    require_mutation_authorization,
    run_mutation_call,
    run_read_call,
)
from ..transformers.accounts import transform_account_types, transform_accounts

#: Descriptor for the read-only account listing operation.
LIST_ACCOUNTS_OPERATION = Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY}))

#: Descriptor for the read-only account type-discovery operation.
ACCOUNT_TYPES_OPERATION = Operation(command="accounts types", effects=frozenset({Effect.READ_ONLY}))


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


def get_account_type_options(
    operation: Operation = ACCOUNT_TYPES_OPERATION,
) -> dict[str, Any]:
    """Fetch the raw account type-discovery response.

    Kept as an explicit raw accessor so callers that offer ``--raw`` never
    import the upstream client directly from a command handler. The response
    is returned untouched (no normalization).

    Args:
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        The upstream response as-is.

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails.
        NetworkError: On timeout or network failure.
    """
    client = get_authenticated_client()
    return cast(dict[str, Any], run_read_call(lambda: client.get_account_type_options(), operation))


def list_account_types(
    operation: Operation = ACCOUNT_TYPES_OPERATION,
) -> list[dict[str, Any]]:
    """Fetch and normalize the supported account group/type/subtype hierarchy.

    Args:
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        Deterministically ordered normalized account type records.

    Raises:
        AuthenticationError: If not authenticated.
        APIError: If API request fails or the response root is not an object.
        NetworkError: On timeout or network failure.
    """
    raw = get_account_type_options(operation)
    return transform_account_types(raw)


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
        After remote execution is attempted, the normative
        ``mutation-outcome.v1`` envelope (see ``core.mutation_outcomes``):
        one ordered item per requested account, a top-level ``succeeded`` or
        ``failed`` status, and a required ``verification`` object when the
        outcome is ambiguous. When no accounts exist, no remote execution is
        attempted and a pre-execution ``no_accounts`` notice is returned
        instead (this is not a mutation outcome).

    Raises:
        AuthenticationError: If not authenticated (pre-execution; stays on
            the structured error path, never becomes a mutation outcome).
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

    # Request refresh (through the shared mutation boundary). The refresh is
    # a single attempt: on timeout/disconnect the outcome is reported as
    # ambiguous (exit 4) rather than a plain failure, with verification
    # guidance for the affected account IDs.
    #
    # The authenticated client is resolved before the mutation attempt (the
    # authorization boundary above still precedes client creation) so a
    # pre-execution authentication failure stays on the structured error
    # path. Any exception raised after the request was attempted is a
    # definite rejection and becomes a failed envelope below; upstream
    # ``request_accounts_refresh`` reports rejection by raising, never by
    # returning a falsy value.
    #
    # Upstream performs one refresh request covering all listed accounts, so
    # per-account outcomes are not independently observable: every item
    # honestly shares the single attempted effect's outcome, preserving the
    # normalized input order.
    _REFRESH_VERIFICATION = (
        "Verify the refresh status for the listed account(s) in the Monarch "
        "web UI (Accounts page) before requesting another refresh; a "
        "pending institution sync may still be in progress."
    )

    client = get_authenticated_client()
    try:
        success = run_mutation_call(
            lambda: client.request_accounts_refresh(account_ids),
            operation,
            entity_ids=tuple(account_ids),
            verification=_REFRESH_VERIFICATION,
        )
    except MutationAmbiguousError as e:
        items = [
            ambiguous_item(
                "account",
                account_id,
                message=(
                    "The refresh request could not be confirmed; remote state "
                    "may have changed. Do not request another refresh before "
                    "verifying."
                ),
                details={
                    "reason": e.details.get("reason"),
                    "remote_state": "unknown",
                },
            )
            for account_id in account_ids
        ]
        return build_mutation_outcome(
            operation.command,
            items,
            verification=verification_object(
                e.details.get(
                    "verification",
                    "Verify the account(s) in the Monarch web UI before "
                    "requesting another refresh.",
                ),
                # No observational refresh-status command exists yet, so no
                # safe verification command can be tokenized here.
                command=None,
            ),
        )
    except Exception as e:  # noqa: BLE001 - classified by the contract
        # Definite rejection after the request was attempted: the refresh
        # did not succeed and the rejection is not ambiguous. The error
        # object is sanitized by the shared contract helper, so arbitrary
        # upstream exception text never reaches the envelope.
        error = error_from_exception(e)
        items = [
            failed_item(
                "account",
                account_id,
                code=error["code"],
                message=error["message"],
                details=error["details"],
            )
            for account_id in account_ids
        ]
        return build_mutation_outcome(operation.command, items)

    if success:
        items = [succeeded_item("account", account_id, {}) for account_id in account_ids]
        return build_mutation_outcome(operation.command, items)

    # The request completed and was definitively not accepted (defensive:
    # upstream reports rejection by raising, handled above): nothing
    # succeeded and the failure is definitive, not ambiguous.
    items = [
        failed_item(
            "account",
            account_id,
            code="API_ERROR",
            message="The refresh request was not accepted by the service.",
            details={},
        )
        for account_id in account_ids
    ]
    return build_mutation_outcome(operation.command, items)
