"""Test-only disposable-fixture adapter for the live mutation suite (mc-584r).

These helpers live in the adapter boundary and are deliberately **not**
registered as public CLI commands. They mutate only the account and
transaction created for one run; existing categories may be referenced
read-only but are never edited or deleted.

Every fixture mutation flows through the shared production machinery so test
code cannot bypass policy:

- explicit :class:`Operation` descriptors containing ``remote_mutation``,
- the shared per-invocation authorization (``set_mutation_authorized``),
- the single-attempt / no-unsafe-retry mutation executor with the shared
  ambiguity classification and sanitized errors,
- the ``mutation-outcome.v1`` builder for normalized results.

The only fixture effect driven through the public installed CLI is the
transaction-notes update; identity, create, and delete use these helpers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from gql import gql

from monarch_cli.core.exceptions import MutationAmbiguousError
from monarch_cli.core.mutation_outcomes import (
    STATUS_AMBIGUOUS,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    ambiguous_item,
    build_mutation_outcome,
    error_from_exception,
    failed_item,
    succeeded_item,
    verification_object,
)
from monarch_cli.core.operations import (
    Effect,
    MutationBlockedError,
    Operation,
    PolicyViolationError,
    mutations_authorized,
    run_mutation_call,
    run_read_call,
    set_mutation_authorized,
)

# --- Explicit fixture operation descriptors ---------------------------------

#: Fixture account creation (real remote effect; test-only operation name).
FIXTURE_ACCOUNT_CREATE = Operation(
    command="live-fixture account create",
    effects=frozenset({Effect.REMOTE_MUTATION}),
)
#: Fixture transaction creation (real remote effect; test-only operation name).
FIXTURE_TRANSACTION_CREATE = Operation(
    command="live-fixture transaction create",
    effects=frozenset({Effect.REMOTE_MUTATION}),
)
#: Fixture transaction deletion.
FIXTURE_TRANSACTION_DELETE = Operation(
    command="live-fixture transaction delete",
    effects=frozenset({Effect.REMOTE_MUTATION}),
)
#: Fixture account deletion.
FIXTURE_ACCOUNT_DELETE = Operation(
    command="live-fixture account delete",
    effects=frozenset({Effect.REMOTE_MUTATION}),
)

#: Read-only fixture context lookups (never mutations).
HOUSEHOLD_LOOKUP = Operation(
    command="live-fixture household lookup",
    effects=frozenset({Effect.READ_ONLY}),
)
CATEGORY_REFERENCE_LOOKUP = Operation(
    command="live-fixture category reference",
    effects=frozenset({Effect.READ_ONLY}),
)
TRANSACTION_NOTES_READ = Operation(
    command="live-fixture transaction notes read",
    effects=frozenset({Effect.READ_ONLY}),
)
TRANSACTION_MARKER_LOOKUP = Operation(
    command="live-fixture transaction marker lookup",
    effects=frozenset({Effect.READ_ONLY}),
)
ACCOUNT_MARKER_LOOKUP = Operation(
    command="live-fixture account marker lookup",
    effects=frozenset({Effect.READ_ONLY}),
)

#: Minimal identity query: only ``myHousehold { id }``. It must never fetch
#: members, accounts, credit, profile, or third-party fields.
_HOUSEHOLD_IDENTITY_QUERY = """
query LiveFixtureHouseholdIdentity {
  myHousehold {
    id
    __typename
  }
}
"""

#: Bounded transaction-detail readback: only the id and notes of one record.
_TRANSACTION_NOTES_QUERY = """
query LiveFixtureTransactionNotes($id: UUID!) {
  getTransaction(id: $id) {
    id
    notes
    __typename
  }
}
"""


class FixtureReadbackError(RuntimeError):
    """A bounded fixture readback did not return the expected shape."""


@dataclass(frozen=True)
class FixtureMutationResult:
    """Normalized result of one fixture mutation attempt."""

    operation: str
    status: str
    envelope: dict[str, Any]
    remote_id: str | None

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_SUCCEEDED


@contextmanager
def fixture_mutation_authorization() -> Iterator[None]:
    """Grant the shared per-invocation mutation authorization for fixtures.

    The dedicated live-mutation gate (marker selection + dedicated opt-in +
    exact household verification) must already have passed before entering;
    this only activates the same authorization flag that ``--allow-mutations``
    sets for a public CLI invocation, and it is always restored on exit.
    """
    previous = mutations_authorized()
    set_mutation_authorized(True)
    try:
        yield
    finally:
        set_mutation_authorized(previous)


def _fixture_verification(operation: str) -> str:
    return (
        f"Fixture operation '{operation}' may have been dispatched. Do not retry "
        "blindly: use the recovery manifest's run marker for a bounded read-only "
        "lookup and inspect the disposable household before retrying."
    )


class LiveFixtureAdapter:
    """Thin, policy-preserving wrapper around the authenticated client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    # --- Read-only context --------------------------------------------------

    def household_id(self) -> str:
        """Return the authenticated household ID via a minimal read-only query.

        Only ``myHousehold { id }`` is requested. A response missing a usable
        string ID fails closed. Comparison against the approved value is the
        caller's responsibility (see ``verify_household_identity``).
        """
        response = run_read_call(
            lambda: self._client.gql_call(
                operation="LiveFixtureHouseholdIdentity",
                graphql_query=gql(_HOUSEHOLD_IDENTITY_QUERY),
                variables={},
            ),
            HOUSEHOLD_LOOKUP,
        )
        household = response.get("myHousehold") if isinstance(response, dict) else None
        observed = household.get("id") if isinstance(household, dict) else None
        if not isinstance(observed, str) or not observed:
            raise FixtureReadbackError(
                "Household identity lookup did not return a usable ID; refusing "
                "to derive identity from any other record."
            )
        return observed

    def reference_category_id(self) -> str | None:
        """Return an existing category ID for transaction creation, read-only.

        The category is only referenced; it is never edited or deleted. Returns
        ``None`` when the account exposes no category.
        """
        response = run_read_call(
            lambda: self._client.get_transaction_categories(),
            CATEGORY_REFERENCE_LOOKUP,
        )
        categories = response.get("categories") if isinstance(response, dict) else None
        for category in categories or []:
            if isinstance(category, dict):
                category_id = category.get("id")
                if isinstance(category_id, str) and category_id:
                    return category_id
        return None

    def read_transaction_notes(self, transaction_id: str) -> str | None:
        """Bounded readback of only one transaction's notes."""
        response = run_read_call(
            lambda: self._client.gql_call(
                operation="LiveFixtureTransactionNotes",
                graphql_query=gql(_TRANSACTION_NOTES_QUERY),
                variables={"id": transaction_id},
            ),
            TRANSACTION_NOTES_READ,
        )
        transaction = response.get("getTransaction") if isinstance(response, dict) else None
        if not isinstance(transaction, dict):
            raise FixtureReadbackError(
                "Bounded transaction readback did not return the fixture transaction."
            )
        notes = transaction.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise FixtureReadbackError("Bounded transaction readback returned malformed notes.")
        return notes

    def find_transaction_ids_by_marker(self, marker: str, *, limit: int = 5) -> list[str]:
        """Bounded read-only marker lookup for ambiguous transaction creations."""
        response = run_read_call(
            lambda: self._client.get_transactions(limit=limit, search=marker),
            TRANSACTION_MARKER_LOOKUP,
        )
        return _collect_ids(response, container="allTransactions", item_key="results")

    def find_account_ids_by_marker(self, marker: str, *, scan_limit: int = 100) -> list[str]:
        """Bounded read-only marker lookup for ambiguous account creations."""
        response = run_read_call(
            lambda: self._client.get_accounts(),
            ACCOUNT_MARKER_LOOKUP,
        )
        accounts = response.get("accounts") if isinstance(response, dict) else None
        matches: list[str] = []
        for account in list(accounts or [])[:scan_limit]:
            if not isinstance(account, dict):
                continue
            name = account.get("displayName")
            account_id = account.get("id")
            if (
                isinstance(name, str)
                and marker in name
                and isinstance(account_id, str)
                and account_id
                and account_id not in matches
            ):
                matches.append(account_id)
        return matches

    # --- Fixture mutations --------------------------------------------------

    def create_manual_account(self, *, marker: str, name: str) -> FixtureMutationResult:
        """Create a uniquely named zero-balance manual asset account."""

        def extract(response: Any) -> str | None:
            payload = response.get("createManualAccount") if isinstance(response, dict) else None
            account = payload.get("account") if isinstance(payload, dict) else None
            account_id = account.get("id") if isinstance(account, dict) else None
            return account_id if isinstance(account_id, str) and account_id else None

        return self._run_mutation(
            operation=FIXTURE_ACCOUNT_CREATE,
            entity="account",
            target_ids=(marker,),
            call_factory=lambda: self._client.create_manual_account(
                account_type="other_asset",
                account_sub_type="other_asset",
                is_in_net_worth=False,
                account_name=name,
                account_balance=0,
            ),
            extract=extract,
            success_result={"run_marker": marker},
        )

    def create_manual_transaction(
        self,
        *,
        marker: str,
        account_id: str,
        category_id: str,
        date: str,
        amount: float = 0.0,
    ) -> FixtureMutationResult:
        """Create a uniquely marked zero-balance manual transaction."""

        def extract(response: Any) -> str | None:
            payload = response.get("createTransaction") if isinstance(response, dict) else None
            transaction = payload.get("transaction") if isinstance(payload, dict) else None
            transaction_id = transaction.get("id") if isinstance(transaction, dict) else None
            return transaction_id if isinstance(transaction_id, str) and transaction_id else None

        return self._run_mutation(
            operation=FIXTURE_TRANSACTION_CREATE,
            entity="transaction",
            target_ids=(marker,),
            call_factory=lambda: self._client.create_transaction(
                date=date,
                account_id=account_id,
                amount=amount,
                merchant_name=f"MC584R fixture {marker}",
                category_id=category_id,
                notes=f"live-fixture:{marker}:created",
            ),
            extract=extract,
            success_result={"run_marker": marker, "account_id": account_id},
        )

    def delete_transaction(self, transaction_id: str) -> FixtureMutationResult:
        """Delete only the fixture transaction created for this run."""

        def extract(response: Any) -> str | None:
            # upstream returns True on success and raises on a definitive error.
            return transaction_id if response is True else None

        return self._run_mutation(
            operation=FIXTURE_TRANSACTION_DELETE,
            entity="transaction",
            target_ids=(transaction_id,),
            call_factory=lambda: self._client.delete_transaction(transaction_id=transaction_id),
            extract=extract,
            success_result={"deleted": True},
        )

    def delete_account(self, account_id: str) -> FixtureMutationResult:
        """Delete only the fixture account created for this run."""

        def extract(response: Any) -> str | None:
            payload = response.get("deleteAccount") if isinstance(response, dict) else None
            return account_id if isinstance(payload, dict) and payload.get("deleted") else None

        return self._run_mutation(
            operation=FIXTURE_ACCOUNT_DELETE,
            entity="account",
            target_ids=(account_id,),
            call_factory=lambda: self._client.delete_account(account_id=account_id),
            extract=extract,
            success_result={"deleted": True},
        )

    # --- Shared execution ---------------------------------------------------

    def _run_mutation(
        self,
        *,
        operation: Operation,
        entity: str,
        target_ids: tuple[str, ...],
        call_factory: Callable[[], Any],
        extract: Callable[[Any], str | None],
        success_result: dict[str, Any],
    ) -> FixtureMutationResult:
        """Execute one fixture effect through the shared mutation boundary."""
        verification = _fixture_verification(operation.command)
        try:
            response = run_mutation_call(
                call_factory,
                operation,
                entity_ids=target_ids,
                verification=verification,
            )
        except MutationAmbiguousError as e:
            item = ambiguous_item(
                entity,
                target_ids[0],
                message=e.message,
                details={
                    "reason": e.details.get("reason"),
                    "remote_state": "unknown",
                },
            )
            return FixtureMutationResult(
                operation=operation.command,
                status=STATUS_AMBIGUOUS,
                envelope=build_mutation_outcome(
                    operation.command,
                    [item],
                    verification=verification_object(verification),
                ),
                remote_id=None,
            )
        except (MutationBlockedError, PolicyViolationError):
            # A blocked or misclassified fixture mutation is a harness error,
            # never reported as a remote failure.
            raise
        except Exception as e:  # noqa: BLE001 - classified by the contract
            error = error_from_exception(e)
            item = failed_item(
                entity,
                target_ids[0],
                code=error["code"],
                message=error["message"],
                details=error["details"],
            )
            return FixtureMutationResult(
                operation=operation.command,
                status=STATUS_FAILED,
                envelope=build_mutation_outcome(operation.command, [item]),
                remote_id=None,
            )

        remote_id = extract(response)
        if remote_id is None:
            # The request was dispatched and returned an unusable identity:
            # creation/deletion may have succeeded, so this is ambiguous and
            # requires a bounded marker lookup before any retry.
            item = ambiguous_item(
                entity,
                target_ids[0],
                message=(
                    f"Fixture operation '{operation.command}' returned no usable "
                    "remote ID; remote state is unknown. Do not retry blindly; use "
                    "the run marker for a bounded read-only lookup."
                ),
                details={"reason": "missing_remote_id", "remote_state": "unknown"},
            )
            return FixtureMutationResult(
                operation=operation.command,
                status=STATUS_AMBIGUOUS,
                envelope=build_mutation_outcome(
                    operation.command,
                    [item],
                    verification=verification_object(verification),
                ),
                remote_id=None,
            )

        item = succeeded_item(entity, remote_id, success_result)
        return FixtureMutationResult(
            operation=operation.command,
            status=STATUS_SUCCEEDED,
            envelope=build_mutation_outcome(operation.command, [item]),
            remote_id=remote_id,
        )


def _collect_ids(response: Any, *, container: str, item_key: str) -> list[str]:
    if not isinstance(response, dict):
        return []
    wrapper = response.get(container)
    if not isinstance(wrapper, dict):
        return []
    ids: list[str] = []
    for item in wrapper.get(item_key) or []:
        if isinstance(item, dict):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id and item_id not in ids:
                ids.append(item_id)
    return ids


__all__ = [
    "FIXTURE_ACCOUNT_CREATE",
    "FIXTURE_TRANSACTION_CREATE",
    "FIXTURE_TRANSACTION_DELETE",
    "FIXTURE_ACCOUNT_DELETE",
    "HOUSEHOLD_LOOKUP",
    "CATEGORY_REFERENCE_LOOKUP",
    "TRANSACTION_NOTES_READ",
    "FixtureReadbackError",
    "FixtureMutationResult",
    "fixture_mutation_authorization",
    "LiveFixtureAdapter",
]
