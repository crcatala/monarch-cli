"""Narrow local GraphQL adapter for explicit transaction review-state writes.

Payload-shape decision (mc-e49c)
================================

The released upstream helper ``MonarchMoney.update_transaction``
(monarchmoneycommunity 1.5.2) unconditionally serializes ``category: null`` and
``name: null`` into the ``UpdateTransactionMutationInput`` even when the caller
supplies only review state. The ticket specifies an ordered resolution, and the
implemented option is recorded here:

1. **Prefer a released upstream fix that omits unrelated fields.** Not
   available: 1.5.2 is the newest published ``monarchmoneycommunity`` release,
   and it still emits the two nulls.
2. **Accept the public helper with controlled evidence that the nulls are
   harmless.** Rejected: this cannot satisfy the ticket's acceptance criterion
   that the serialized mutation input contain *only* transaction identity and
   the one intended review-state field, because the helper always emits those
   two extra keys.
3. **Maintain a narrow local GraphQL adapter with explicit query-shape
   compatibility tests and documented maintenance ownership.** Chosen.

This module is resolution option 3. It is deliberately *not* a monkeypatch or
interception of the upstream ``gql_call``: it calls the public
``MonarchMoney.gql_call`` transport method with an explicit, minimal document
whose only operation variable is transaction identity plus the single intended
review field. There is no hidden coupling to the upstream helper's private
operation or variable structure; the document below is the complete contract.

Maintenance ownership
=====================

The monarch-cli maintainers own this adapter. The GraphQL document, operation
name, variable shape, and response selection set are pinned by
``tests/core/test_review_mutation.py``. Changing any of them requires a
deliberate update to those query-shape compatibility tests and a re-review of
the upstream ``updateTransaction`` mutation contract. When upstream releases a
public helper that emits only the intended field, prefer deleting this adapter
and consuming that helper instead.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, cast

from gql import gql

#: Upstream mutation operation label. Deliberately identical to the released
#: helper's label so the server-side mutation field (``updateTransaction``) and
#: its observed operation are unchanged; only the input variables and the
#: response selection set are narrowed.
OPERATION_NAME = "Web_TransactionDrawerUpdateTransaction"

#: The minimal mutation document. It selects only identity plus the observed
#: review fields for the write response; the authoritative post-write read is
#: ``get_transaction_details``. It intentionally omits every unrelated mutable
#: input (category, merchant, amount, date, notes, goal, hideFromReports).
REVIEW_MUTATION_QUERY = """
mutation Web_TransactionDrawerUpdateTransaction($input: UpdateTransactionMutationInput!) {
  updateTransaction(input: $input) {
    transaction {
      id
      needsReview
      reviewedAt
      reviewedByUser {
        id
        name
      }
    }
    errors {
      fieldErrors {
        field
        messages
      }
      message
      code
    }
  }
}
"""

REVIEW_MUTATION_DOCUMENT = gql(REVIEW_MUTATION_QUERY)


class ReviewIntent(StrEnum):
    """The two supported, intent-oriented transaction review actions."""

    MARK_REVIEWED = "mark_reviewed"
    RETURN_TO_QUEUE = "return_to_queue"


#: Intent -> the single upstream input field it maps to. Exactly one field is
#: ever sent; ``reviewed=False`` / ``needsReview=False`` are never emitted.
_INTENT_FIELD: dict[ReviewIntent, str] = {
    ReviewIntent.MARK_REVIEWED: "reviewed",
    ReviewIntent.RETURN_TO_QUEUE: "needsReview",
}


def build_review_variables(transaction_id: str, intent: ReviewIntent) -> dict[str, Any]:
    """Build the exact mutation variables for one intent.

    The returned mapping contains transaction identity and the one intended
    review-state field only. It is the whole serialized ``input`` object, so a
    full-variable assertion can prove no unrelated category, merchant, or other
    mutable field is ever sent.
    """
    field = _INTENT_FIELD[intent]
    return {"input": {"id": transaction_id, field: True}}


async def set_transaction_review_state(
    client: Any,
    transaction_id: str,
    intent: ReviewIntent,
) -> dict[str, Any]:
    """Dispatch one exact review-state mutation through the public transport.

    Args:
        client: Authenticated ``MonarchMoney`` client (only its public
            ``gql_call`` transport method is used).
        transaction_id: Exact transaction target.
        intent: Which intent-oriented review action to apply.

    Returns:
        The raw GraphQL response data mapping (``{"updateTransaction": {...}}``).
    """
    result = await client.gql_call(
        operation=OPERATION_NAME,
        graphql_query=REVIEW_MUTATION_DOCUMENT,
        variables=build_review_variables(transaction_id, intent),
    )
    return cast(dict[str, Any], result)


__all__ = [
    "OPERATION_NAME",
    "REVIEW_MUTATION_QUERY",
    "REVIEW_MUTATION_DOCUMENT",
    "ReviewIntent",
    "build_review_variables",
    "set_transaction_review_state",
]
