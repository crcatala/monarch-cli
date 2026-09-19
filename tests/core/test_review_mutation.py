"""Query-shape compatibility tests for the narrow review-mutation adapter (mc-e49c).

These tests pin the explicit local GraphQL contract chosen as resolution
option 3 of the ticket: the adapter must serialize only transaction identity
and the one intended review-state field, never the unrelated ``category`` /
``name`` nulls the released upstream helper emits. They also document the
maintenance boundary: if the document or variable shape changes, these tests
must be updated deliberately.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from gql import gql

from monarch_cli.core.review_mutation import (
    OPERATION_NAME,
    REVIEW_MUTATION_DOCUMENT,
    REVIEW_MUTATION_QUERY,
    ReviewIntent,
    build_review_variables,
    set_transaction_review_state,
)

UNRELATED_INPUT_FIELDS = (
    "category",
    "name",
    "amount",
    "date",
    "notes",
    "goalId",
    "hideFromReports",
    "merchant",
)


def test_intent_enum_is_exactly_the_two_intents() -> None:
    assert set(ReviewIntent) == {ReviewIntent.MARK_REVIEWED, ReviewIntent.RETURN_TO_QUEUE}


def test_document_is_a_single_update_transaction_mutation() -> None:
    document = gql(REVIEW_MUTATION_QUERY)
    operations = [definition.name.value for definition in document.document.definitions]
    assert operations == [OPERATION_NAME]
    assert "$input: UpdateTransactionMutationInput!" in REVIEW_MUTATION_QUERY
    assert "updateTransaction(input: $input)" in REVIEW_MUTATION_QUERY
    # The document must not declare any unrelated mutable variable.
    for field in UNRELATED_INPUT_FIELDS:
        assert f"${field}" not in REVIEW_MUTATION_QUERY
    assert REVIEW_MUTATION_DOCUMENT is not None


def test_mark_reviewed_serializes_only_identity_and_reviewed() -> None:
    variables = build_review_variables("txn-1", ReviewIntent.MARK_REVIEWED)
    assert variables == {"input": {"id": "txn-1", "reviewed": True}}
    assert set(variables["input"]) == {"id", "reviewed"}


def test_return_to_queue_serializes_only_identity_and_needs_review() -> None:
    variables = build_review_variables("txn-1", ReviewIntent.RETURN_TO_QUEUE)
    assert variables == {"input": {"id": "txn-1", "needsReview": True}}
    assert set(variables["input"]) == {"id", "needsReview"}


@pytest.mark.parametrize("intent", list(ReviewIntent))
def test_full_variables_never_contain_unrelated_or_false_values(intent: ReviewIntent) -> None:
    """A full-variable assertion fails if any unrelated field is ever sent."""
    serialized = build_review_variables("txn-1", intent)["input"]
    for field in UNRELATED_INPUT_FIELDS:
        assert field not in serialized
    # The one intended field is always the boolean True; the CLI never emits
    # ``reviewed=False`` / ``needsReview=False``.
    review_fields = {key: value for key, value in serialized.items() if key != "id"}
    assert review_fields in ({"reviewed": True}, {"needsReview": True})


@pytest.mark.asyncio
async def test_adapter_dispatches_exact_transport_arguments() -> None:
    client = AsyncMock()
    client.gql_call.return_value = {"updateTransaction": {"errors": None}}
    result = await set_transaction_review_state(client, "txn-9", ReviewIntent.MARK_REVIEWED)
    client.gql_call.assert_awaited_once_with(
        operation=OPERATION_NAME,
        graphql_query=REVIEW_MUTATION_DOCUMENT,
        variables={"input": {"id": "txn-9", "reviewed": True}},
    )
    assert result == {"updateTransaction": {"errors": None}}
