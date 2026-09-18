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
from ..core.dates import parse_iso_date, validate_date_ordering
from ..core.exceptions import MutationAmbiguousError, ValidationError
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
from ..transformers.accounts import (
    transform_account_history,
    transform_account_types,
    transform_accounts,
    transform_aggregate_snapshots,
    transform_recent_balances,
    transform_snapshots_by_type,
)

#: Descriptor for the read-only account listing operation.
LIST_ACCOUNTS_OPERATION = Operation(command="accounts list", effects=frozenset({Effect.READ_ONLY}))

#: Descriptor for the read-only account type-discovery operation.
ACCOUNT_TYPES_OPERATION = Operation(command="accounts types", effects=frozenset({Effect.READ_ONLY}))

#: Descriptor for the read-only single-account history operation.
ACCOUNT_HISTORY_OPERATION = Operation(
    command="accounts history", effects=frozenset({Effect.READ_ONLY})
)

#: Descriptor for the read-only recent-balances operation.
RECENT_BALANCES_OPERATION = Operation(
    command="accounts recent-balances", effects=frozenset({Effect.READ_ONLY})
)

#: Descriptor for the read-only aggregate snapshots operation.
AGGREGATE_SNAPSHOTS_OPERATION = Operation(
    command="accounts snapshots", effects=frozenset({Effect.READ_ONLY})
)

#: Descriptor for the read-only type-scoped snapshots operation.
SNAPSHOTS_BY_TYPE_OPERATION = Operation(
    command="accounts snapshots-by-type", effects=frozenset({Effect.READ_ONLY})
)

#: Descriptor for the observational refresh-status operation. Never initiates
#: or waits for a refresh; ``accounts refresh`` remains the separate
#: ``remote_mutation`` operation.
REFRESH_STATUS_OPERATION = Operation(
    command="accounts refresh-status", effects=frozenset({Effect.READ_ONLY})
)


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


def _require_identifier(value: str, field: str) -> str:
    """Validate that an identifier is a non-empty opaque string.

    Identifiers are opaque: the value is passed to the API unchanged and is
    never coerced to an integer (the upstream ``get_account_history`` type
    annotation is inaccurate; the released client stringifies internally).

    Args:
        value: The raw identifier value.
        field: CLI option/argument name used in error messages.

    Returns:
        The unchanged identifier value.

    Raises:
        ValidationError: If the identifier is empty or whitespace-only.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            message=f"--{field} must be a non-empty account ID.",
            field=field,
        )
    return value


def get_account_history(
    account_id: str,
    *,
    raw: bool = False,
    operation: Operation = ACCOUNT_HISTORY_OPERATION,
) -> list[dict[str, Any]] | Any:
    """Fetch one account's balance history for an opaque string account ID.

    Args:
        account_id: Opaque non-empty upstream account identifier. Never
            coerced to an integer.
        raw: When ``True``, return the single upstream response untouched.
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        The normalized history records (see
        ``transform_account_history``), or the raw upstream response when
        ``raw`` is set.

    Raises:
        ValidationError: If the identifier is empty or whitespace-only.
        AuthenticationError: If not authenticated.
        APIError: If the API request fails or the response is malformed.
        NetworkError: On timeout or network failure.
    """
    _require_identifier(account_id, "account")
    client = get_authenticated_client()
    data = run_read_call(lambda: client.get_account_history(account_id), operation)
    return data if raw else transform_account_history(data)


def get_recent_account_balances(
    start_date: str | None = None,
    *,
    raw: bool = False,
    operation: Operation = RECENT_BALANCES_OPERATION,
) -> list[dict[str, Any]] | Any:
    """Fetch recent daily balances for all accounts from a start date.

    The released upstream method accepts a start date only; there is no
    end-date filter, and none is offered or silently dropped here.

    Args:
        start_date: Inclusive ``YYYY-MM-DD`` start date, or ``None`` for the
            upstream default (the last 31 days).
        raw: When ``True``, return the single upstream response untouched.
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        Normalized per-account records (see ``transform_recent_balances``),
        or the raw upstream response when ``raw`` is set.

    Raises:
        ValidationError: If the start date is not a valid ``YYYY-MM-DD`` date.
        AuthenticationError: If not authenticated.
        APIError: If the API request fails or the response is malformed.
        NetworkError: On timeout or network failure.
    """
    if start_date is not None:
        parse_iso_date(start_date, field="start")
    client = get_authenticated_client()
    data = run_read_call(lambda: client.get_recent_account_balances(start_date), operation)
    return data if raw else transform_recent_balances(data)


def get_aggregate_snapshots(
    start_date: str | None,
    end_date: str | None,
    account_type: str | None = None,
    *,
    raw: bool = False,
    operation: Operation = AGGREGATE_SNAPSHOTS_OPERATION,
) -> list[dict[str, Any]] | Any:
    """Fetch aggregate (net-worth) snapshots over a validated date range.

    Both bounds are required by the released upstream method; one-sided
    ranges are rejected before any API call. The optional ``account_type``
    filter is validated against the ``mc-7xfl`` account-type discovery
    surface (no second discovery implementation).

    Args:
        start_date: Inclusive start date, ``YYYY-MM-DD`` (required).
        end_date: Inclusive end date, ``YYYY-MM-DD`` (required).
        account_type: Optional account type identifier as exposed by
            ``accounts types`` (the ``type`` field).
        raw: When ``True``, return the single upstream response untouched.
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        Normalized snapshot records (see ``transform_aggregate_snapshots``),
        or the raw upstream response when ``raw`` is set.

    Raises:
        ValidationError: On a missing/malformed date, an inverted range, or
            an unknown account-type filter value.
        AuthenticationError: If not authenticated.
        APIError: If the API request fails or the response is malformed.
        NetworkError: On timeout or network failure.
    """
    start = parse_iso_date(start_date, field="start")
    end = parse_iso_date(end_date, field="end")
    if start is None or end is None:
        raise ValidationError(
            message="--start and --end are both required for aggregate snapshots; "
            "the upstream aggregate snapshot query does not support one-sided ranges.",
            field="start" if start is None else "end",
        )
    validate_date_ordering(start, end)

    if account_type is not None:
        _validate_account_type_filter(account_type)

    client = get_authenticated_client()
    data = run_read_call(
        lambda: client.get_aggregate_snapshots(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            account_type=account_type,
        ),
        operation,
    )
    return data if raw else transform_aggregate_snapshots(data)


def get_account_snapshots_by_type(
    start_date: str,
    timeframe: str,
    *,
    raw: bool = False,
    operation: Operation = SNAPSHOTS_BY_TYPE_OPERATION,
) -> dict[str, Any] | Any:
    """Fetch type-scoped net-value snapshots from a start date.

    The released upstream method accepts a start date plus a ``month`` or
    ``year`` timeframe; there is no end-date filter. Month-timeframe records
    retain their upstream ``YYYY-MM`` precision.

    Args:
        start_date: Inclusive start date, ``YYYY-MM-DD`` (required).
        timeframe: ``month`` or ``year``.
        raw: When ``True``, return the single upstream response untouched.
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        Normalized snapshot collection (see ``transform_snapshots_by_type``),
        or the raw upstream response when ``raw`` is set.

    Raises:
        ValidationError: On a missing/malformed date or an unsupported
            timeframe.
        AuthenticationError: If not authenticated.
        APIError: If the API request fails or the response is malformed.
        NetworkError: On timeout or network failure.
    """
    if parse_iso_date(start_date, field="start") is None:
        raise ValidationError(message="--start is required.", field="start")
    if timeframe not in ("month", "year"):
        raise ValidationError(
            message=f"--timeframe must be 'month' or 'year' (got '{timeframe}').",
            field="timeframe",
        )

    client = get_authenticated_client()
    data = run_read_call(
        lambda: client.get_account_snapshots_by_type(start_date, timeframe),
        operation,
    )
    return data if raw else transform_snapshots_by_type(data)


def _validate_account_type_filter(account_type: str) -> None:
    """Validate an account-type snapshot filter against ``mc-7xfl`` discovery.

    The check is observational and read-only: it reuses the landed
    ``accounts types`` discovery service rather than implementing a second
    discovery surface. An empty or unknown value fails before the target API
    call.

    Raises:
        ValidationError: If the value is empty or not a known account type.
    """
    _require_identifier(account_type, "account-type")
    known = {record["type"] for record in list_account_types() if record.get("type")}
    if account_type not in known:
        raise ValidationError(
            message=(
                f"Unknown account type '{account_type}'. "
                "Run 'monarch accounts types' for supported identifiers."
            ),
            field="account-type",
            details={"valid_types": sorted(t for t in known if t)},
        )


def get_refresh_status(
    account_ids: list[str] | None = None,
    *,
    operation: Operation = REFRESH_STATUS_OPERATION,
) -> dict[str, Any]:
    """Observationally inspect account refresh completion.

    This never initiates or waits for a refresh; it only reports the
    upstream ``hasSyncInProgress`` aggregate state. Requested account IDs are
    validated against account discovery before the status check: unknown IDs
    are reported explicitly and never folded into a ``complete: true``
    result (the released client's aggregate boolean would mask an
    empty selection as complete).

    Args:
        account_ids: Optional opaque account IDs to check. ``None`` checks
            every discovered account.
        operation: Explicit descriptor for the invoking read operation.

    Returns:
        Dict with stable keys:

        - ``status``: ``"complete"``, ``"in_progress"``, or ``"unknown"``.
        - ``complete``: Aggregate boolean, or ``null`` when unknown.
        - ``requested_account_ids``: The requested IDs, or ``None``.
        - ``known_account_ids``: Requested IDs found in discovery (all
            checked IDs when no explicit request was made).
        - ``unknown_account_ids``: Requested IDs not found in discovery.
        - ``checked_account_count``: Number of accounts whose status was
            actually inspected.

    Raises:
        ValidationError: If any requested identifier is empty.
        AuthenticationError: If not authenticated.
        APIError: If an API request fails.
        NetworkError: On timeout or network failure.
    """
    unknown: list[str] = []
    checked: list[str] = []
    requested: list[str] | None = None

    if account_ids is not None:
        for account_id in account_ids:
            _require_identifier(account_id, "account")
        # Deduplicate while preserving the caller's order.
        requested = list(dict.fromkeys(account_ids))
        discovered = list_accounts()
        known_ids = {acc["id"] for acc in discovered if acc.get("id")}
        unknown = [acc_id for acc_id in requested if acc_id not in known_ids]
        checked = [acc_id for acc_id in requested if acc_id in known_ids]
        if unknown:
            # Unknown requested IDs must never collapse into a successful
            # completion: report them explicitly and skip the status call.
            return {
                "status": "unknown",
                "complete": None,
                "requested_account_ids": requested,
                "known_account_ids": checked,
                "unknown_account_ids": unknown,
                "checked_account_count": 0,
            }
    else:
        discovered = list_accounts()
        checked = [acc["id"] for acc in discovered if acc.get("id")]
        requested = None

    if not checked:
        # No accounts exist at all: nothing can be syncing. The empty
        # selection is reported honestly with a zero checked count rather
        # than being folded through an unknown-ID mask.
        return {
            "status": "complete",
            "complete": True,
            "requested_account_ids": requested,
            "known_account_ids": checked,
            "unknown_account_ids": [],
            "checked_account_count": 0,
        }

    client = get_authenticated_client()
    complete = bool(run_read_call(lambda: client.is_accounts_refresh_complete(checked), operation))
    return {
        "status": "complete" if complete else "in_progress",
        "complete": complete,
        "requested_account_ids": requested,
        "known_account_ids": checked,
        "unknown_account_ids": [],
        "checked_account_count": len(checked),
    }
