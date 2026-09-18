"""Unit tests for the disposable-fixture adapter (mc-584r).

Non-live: no API calls. A fake async client returns canned upstream-shaped
responses so the adapter's policy preservation, outcome mapping, ambiguity
classification, bounded readback, and minimal identity query can be exercised
without touching the network.
"""

from __future__ import annotations

from typing import Any

import pytest

from monarch_cli.core.exceptions import MutationAmbiguousError
from monarch_cli.core.mutation_outcomes import (
    STATUS_AMBIGUOUS,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
)
from monarch_cli.core.operations import (
    MutationBlockedError,
    PolicyViolationError,
    reset_mutation_authorization,
)
from tests.live import live_fixture_adapter as adapter_mod
from tests.live.live_fixture_adapter import (
    FIXTURE_ACCOUNT_CREATE,
    FIXTURE_ACCOUNT_DELETE,
    FIXTURE_TRANSACTION_CREATE,
    FIXTURE_TRANSACTION_DELETE,
    FixtureReadbackError,
    LiveFixtureAdapter,
    fixture_mutation_authorization,
)


@pytest.fixture(autouse=True)
def _reset_auth() -> Any:
    reset_mutation_authorization()
    yield
    reset_mutation_authorization()


class FakeClient:
    """Async stand-in for the authenticated MonarchMoney client."""

    def __init__(self, **responses: Any) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.query_capture: list[tuple[str, str]] = []

    def _next(self, name: str, **kwargs: Any) -> Any:
        self.calls.append((name, kwargs))
        response = self.responses[name]
        if isinstance(response, BaseException):
            raise response
        return response

    async def create_manual_account(self, **kwargs: Any) -> Any:
        return self._next("create_manual_account", **kwargs)

    async def create_transaction(self, **kwargs: Any) -> Any:
        return self._next("create_transaction", **kwargs)

    async def delete_transaction(self, **kwargs: Any) -> Any:
        return self._next("delete_transaction", **kwargs)

    async def delete_account(self, **kwargs: Any) -> Any:
        return self._next("delete_account", **kwargs)

    async def get_transaction_categories(self) -> Any:
        return self._next("get_transaction_categories")

    async def get_accounts(self) -> Any:
        return self._next("get_accounts")

    async def get_transactions(self, **kwargs: Any) -> Any:
        return self._next("get_transactions", **kwargs)

    async def gql_call(self, operation: str, graphql_query: Any, variables: Any = None) -> Any:
        from graphql import print_ast

        # gql 4.x returns a GraphQLRequest wrapping the parsed document.
        document = getattr(graphql_query, "document", graphql_query)
        self.query_capture.append((operation, print_ast(document)))
        self.last_variables = variables
        return self._next("gql_call")


# --- Minimal identity query -------------------------------------------------


def test_household_identity_query_requests_only_id() -> None:
    query = adapter_mod._HOUSEHOLD_IDENTITY_QUERY
    for forbidden in (
        "members",
        "accounts",
        "credit",
        "profile",
        "balance",
        "email",
        "transactions",
    ):
        assert forbidden not in query.lower()
    assert "myHousehold" in query


def test_household_id_uses_minimal_lookup() -> None:
    client = FakeClient(gql_call={"myHousehold": {"id": "hh-1"}})
    adapter = LiveFixtureAdapter(client)
    assert adapter.household_id() == "hh-1"
    assert client.query_capture[0][0] == "LiveFixtureHouseholdIdentity"
    assert "members" not in client.query_capture[0][1].lower()
    assert "credit" not in client.query_capture[0][1].lower()


def test_household_id_missing_fails_closed() -> None:
    client = FakeClient(gql_call={"myHousehold": {}})
    adapter = LiveFixtureAdapter(client)
    with pytest.raises(FixtureReadbackError):
        adapter.household_id()


# --- Read-only helpers ------------------------------------------------------


def test_reference_category_id_returns_first_category() -> None:
    client = FakeClient(get_transaction_categories={"categories": [{"id": "cat-1"}]})
    assert LiveFixtureAdapter(client).reference_category_id() == "cat-1"


def test_reference_category_id_returns_none_when_absent() -> None:
    client = FakeClient(get_transaction_categories={"categories": []})
    assert LiveFixtureAdapter(client).reference_category_id() is None


def test_read_transaction_notes_bounded_readback() -> None:
    client = FakeClient(gql_call={"getTransaction": {"id": "txn-1", "notes": "hello"}})
    assert LiveFixtureAdapter(client).read_transaction_notes("txn-1") == "hello"


def test_read_transaction_notes_missing_transaction_fails() -> None:
    client = FakeClient(gql_call={"getTransaction": None})
    with pytest.raises(FixtureReadbackError):
        LiveFixtureAdapter(client).read_transaction_notes("txn-1")


def test_read_transaction_notes_malformed_notes_fails() -> None:
    client = FakeClient(gql_call={"getTransaction": {"id": "txn-1", "notes": 5}})
    with pytest.raises(FixtureReadbackError):
        LiveFixtureAdapter(client).read_transaction_notes("txn-1")


# --- Policy preservation ----------------------------------------------------


def test_fixture_mutation_requires_authorization() -> None:
    client = FakeClient(
        create_manual_account={"createManualAccount": {"account": {"id": "acct-1"}}}
    )
    adapter = LiveFixtureAdapter(client)
    with pytest.raises(MutationBlockedError):
        adapter.create_manual_account(marker="m", name="n")
    assert client.calls == []


def test_fixture_mutation_authorization_restores_previous() -> None:
    from monarch_cli.core.operations import mutations_authorized

    assert mutations_authorized() is False
    with fixture_mutation_authorization():
        assert mutations_authorized() is True
    assert mutations_authorized() is False


def test_read_executor_refuses_mutation_operation() -> None:
    client = FakeClient(create_manual_account={"createManualAccount": {"account": {"id": "x"}}})
    with pytest.raises(PolicyViolationError):
        from monarch_cli.core.operations import run_read_call

        run_read_call(
            lambda: client.create_manual_account(),
            FIXTURE_ACCOUNT_CREATE,
        )


# --- Outcome mappings -------------------------------------------------------


def test_create_manual_account_success_mapping() -> None:
    client = FakeClient(
        create_manual_account={"createManualAccount": {"account": {"id": "acct-1"}}}
    )
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.create_manual_account(marker="mark", name="name")
    assert result.status == STATUS_SUCCEEDED
    assert result.remote_id == "acct-1"
    assert result.envelope["operation"] == "live-fixture.account.create"
    assert result.envelope["schema_version"] == "mutation-outcome.v1"
    # Zero-balance manual account, not in net worth.
    _, kwargs = client.calls[0]
    assert kwargs["account_balance"] == 0
    assert kwargs["is_in_net_worth"] is False


def test_create_manual_transaction_success_mapping() -> None:
    client = FakeClient(create_transaction={"createTransaction": {"transaction": {"id": "txn-1"}}})
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.create_manual_transaction(
            marker="mark", account_id="acct-1", category_id="cat-1", date="2026-01-01"
        )
    assert result.status == STATUS_SUCCEEDED
    assert result.remote_id == "txn-1"
    assert result.envelope["operation"] == "live-fixture.transaction.create"
    _, kwargs = client.calls[0]
    assert kwargs["amount"] == 0.0
    assert kwargs["category_id"] == "cat-1"
    assert "mark" in kwargs["notes"]


def test_delete_transaction_success_mapping() -> None:
    client = FakeClient(delete_transaction=True)
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.delete_transaction("txn-1")
    assert result.status == STATUS_SUCCEEDED
    assert result.remote_id == "txn-1"
    assert result.envelope["operation"] == "live-fixture.transaction.delete"


def test_delete_account_success_mapping() -> None:
    client = FakeClient(delete_account={"deleteAccount": {"deleted": True}})
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.delete_account("acct-1")
    assert result.status == STATUS_SUCCEEDED
    assert result.remote_id == "acct-1"
    assert result.envelope["operation"] == "live-fixture.account.delete"


def test_definite_failure_mapping() -> None:
    client = FakeClient(delete_account=RuntimeError("upstream rejected"))
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.delete_account("acct-1")
    assert result.status == STATUS_FAILED
    assert result.remote_id is None
    assert result.envelope["status"] == STATUS_FAILED


def test_ambiguous_transport_failure_mapping() -> None:
    client = FakeClient(create_manual_account=TimeoutError())
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.create_manual_account(marker="m", name="n")
    assert result.status == STATUS_AMBIGUOUS
    assert result.remote_id is None
    assert result.envelope["verification"]["required"] is True


def test_missing_remote_id_is_ambiguous() -> None:
    client = FakeClient(create_manual_account={"createManualAccount": {"account": None}})
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.create_manual_account(marker="m", name="n")
    assert result.status == STATUS_AMBIGUOUS


def test_ambiguous_error_from_executor_is_ambiguous() -> None:
    client = FakeClient(
        create_manual_account=MutationAmbiguousError(
            message="unknown",
            details={"reason": "timeout", "entity_ids": ["m"]},
        )
    )
    adapter = LiveFixtureAdapter(client)
    with fixture_mutation_authorization():
        result = adapter.create_manual_account(marker="m", name="n")
    assert result.status == STATUS_AMBIGUOUS


# --- Bounded marker lookups -------------------------------------------------


def test_find_transaction_ids_by_marker_bounded_search() -> None:
    client = FakeClient(
        get_transactions={"allTransactions": {"results": [{"id": "txn-1"}, {"id": "txn-2"}]}}
    )
    adapter = LiveFixtureAdapter(client)
    assert adapter.find_transaction_ids_by_marker("mark") == ["txn-1", "txn-2"]
    _, kwargs = client.calls[0]
    assert kwargs["search"] == "mark"
    assert kwargs["limit"] == 5


def test_find_account_ids_by_marker_filters_by_name() -> None:
    client = FakeClient(
        get_accounts={
            "accounts": [
                {"id": "acct-1", "displayName": "MC584R fixture mark"},
                {"id": "acct-2", "displayName": "Existing savings"},
            ]
        }
    )
    adapter = LiveFixtureAdapter(client)
    assert adapter.find_account_ids_by_marker("mark") == ["acct-1"]


def test_find_account_ids_by_marker_ignores_missing_or_nonstring_names() -> None:
    # Recovery must stay usable when an unrelated account record has no usable
    # display name; a non-string name must never raise out of the lookup.
    client = FakeClient(
        get_accounts={
            "accounts": [
                {"id": "acct-none", "displayName": None},
                {"id": "acct-num", "displayName": 1234},
                "not-a-mapping",
                {"id": "acct-1", "displayName": "MC584R fixture mark"},
            ]
        }
    )
    adapter = LiveFixtureAdapter(client)
    assert adapter.find_account_ids_by_marker("mark") == ["acct-1"]


# --- Operation descriptors are mutations ------------------------------------


def test_fixture_descriptors_declare_remote_mutation() -> None:
    from monarch_cli.core.operations import Effect

    for operation in (
        FIXTURE_ACCOUNT_CREATE,
        FIXTURE_TRANSACTION_CREATE,
        FIXTURE_TRANSACTION_DELETE,
        FIXTURE_ACCOUNT_DELETE,
    ):
        assert Effect.REMOTE_MUTATION in operation.effects
