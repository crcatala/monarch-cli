"""Scanned receipt API contracts from Monarch's web app; synthetic records only."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from graphql import print_ast

from monarch_cli.core.exceptions import APIError, NotFoundError, ValidationError
from monarch_cli.core.receipt_api import fetch_inbox, fetch_receipt, match_receipt


def receipt(*, linked=None, count=1, status="pending_matches"):
    return {
        "id": "r1",
        "vendor": "user_import",
        "status": status,
        "orders": [
            {
                "id": "o1",
                "retailTransactions": [
                    {"id": f"rt{i}", "transaction": {"id": linked} if linked else None}
                    for i in range(count)
                ],
            }
        ],
        "attachments": [],
    }


def client_with(*responses):
    return MagicMock(gql_call=AsyncMock(side_effect=list(responses)))


async def test_inbox_contract_and_pagination():
    client = client_with({"retailSyncsWithTotal": {"totalCount": 8, "results": [receipt()]}})
    data = await fetch_inbox(
        client, limit=1, offset=2, status="pending_matches", order_by="receipt_date"
    )
    call = client.gql_call.call_args.kwargs
    assert call["operation"] == "Common_RetailSyncsQueryWithTotal"
    assert call["variables"] == {
        "filters": {"vendors": ["user_import", "email_import"], "status": "pending_matches"},
        "offset": 2,
        "limit": 1,
        "includeTotalCount": True,
        "orderBy": "receipt_date",
    }
    assert "retailSyncsWithTotal" in print_ast(call["graphql_query"])
    assert data == {
        "results": [receipt()],
        "total_count": 8,
        "offset": 2,
        "limit": 1,
        "next_offset": 3,
    }


async def test_empty_inbox():
    client = client_with({"retailSyncsWithTotal": {"totalCount": 0, "results": []}})
    assert (await fetch_inbox(client))["next_offset"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"retailSyncsWithTotal": None},
        {"retailSyncsWithTotal": {"totalCount": 3, "results": []}},
        {"retailSyncsWithTotal": {"totalCount": True, "results": []}},
        {"retailSyncsWithTotal": {"totalCount": 1, "results": [None]}},
    ],
)
async def test_inbox_rejects_malformed_or_stalled_page(payload):
    with pytest.raises(APIError):
        await fetch_inbox(client_with(payload))


async def test_show_contract():
    client = client_with({"retailSync": receipt()})
    assert await fetch_receipt(client, "r1") == receipt()
    assert client.gql_call.call_args.kwargs["variables"] == {"syncId": "r1"}


async def test_show_not_found():
    with pytest.raises(NotFoundError):
        await fetch_receipt(client_with({"retailSync": None}), "r1")


async def test_match_preview_reads_without_writes():
    client = client_with({"retailSync": receipt()})
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    result = await match_receipt(client, "r1", "t1", dry_run=True)
    assert result["status"] == "dry_run"
    assert result["retail_transaction_id"] == "rt0"
    assert client.gql_call.await_count == 1
    client.get_transaction_details.assert_awaited_once_with(
        transaction_id="t1", redirect_posted=False
    )


async def test_match_write_and_readback():
    client = client_with(
        {"retailSync": receipt()},
        {"matchRetailTransaction": {"retailSync": {"id": "r1"}, "errors": None}},
        {"retailSync": receipt(linked="t1", status="completed")},
    )
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    result = await match_receipt(client, "r1", "t1")
    assert result["status"] == "matched"
    assert result["verified"] is True
    call = client.gql_call.call_args_list[1].kwargs
    assert call["operation"] == "Common_MatchRetailTransaction"
    assert call["variables"] == {"retailTransactionId": "rt0", "transactionId": "t1"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"matchRetailTransaction": None},
        {"matchRetailTransaction": {"retailSync": {"id": "r1"}, "errors": {"message": "denied"}}},
        {"matchRetailTransaction": {"retailSync": {"id": "other"}, "errors": None}},
    ],
)
async def test_match_checks_payload_errors(payload):
    client = client_with({"retailSync": receipt()}, payload)
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    with pytest.raises(APIError):
        await match_receipt(client, "r1", "t1")
    assert client.gql_call.await_count == 2


async def test_match_requires_verified_readback():
    client = client_with(
        {"retailSync": receipt()},
        {"matchRetailTransaction": {"retailSync": {"id": "r1"}, "errors": None}},
        {"retailSync": receipt()},
    )
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    with pytest.raises(APIError, match="verify"):
        await match_receipt(client, "r1", "t1")


@pytest.mark.parametrize(
    "record,retail_id",
    [
        (receipt(count=2), None),
        (receipt(count=0), None),
        (receipt(), "wrong"),
        (receipt(linked="other"), None),
        (receipt(status="in_progress"), None),
        ({**receipt(), "vendor": "amazon"}, None),
        ({**receipt(), "orders": None}, None),
    ],
)
async def test_match_rejects_ambiguous_or_unsafe_targets(record, retail_id):
    client = client_with({"retailSync": record})
    with pytest.raises((ValidationError, APIError)):
        await match_receipt(client, "r1", "t1", retail_transaction_id=retail_id)
    assert client.gql_call.await_count == 1


async def test_explicit_selection_from_multiple_orders():
    record = receipt(count=2)
    other_order = deepcopy(record["orders"][0])
    other_order["retailTransactions"] = [{"id": "rt2", "transaction": None}]
    record["orders"].append(other_order)
    client = client_with({"retailSync": record})
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    result = await match_receipt(client, "r1", "t1", retail_transaction_id="rt2", dry_run=True)
    assert result["retail_transaction_id"] == "rt2"


async def test_match_is_idempotent_for_existing_link():
    client = client_with({"retailSync": receipt(linked="t1", status="completed")})
    result = await match_receipt(client, "r1", "t1")
    assert result["status"] == "already_matched"
    assert client.gql_call.await_count == 1


@pytest.mark.parametrize("target", [None, {}, {"id": "other"}])
async def test_match_rejects_missing_or_redirected_transaction(target):
    client = client_with({"retailSync": receipt()})
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": target})
    with pytest.raises((NotFoundError, APIError)):
        await match_receipt(client, "r1", "t1")
    assert client.gql_call.await_count == 1


async def test_match_rejects_empty_error_object():
    client = client_with(
        {"retailSync": receipt()},
        {"matchRetailTransaction": {"retailSync": {"id": "r1"}, "errors": {}}},
    )
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    with pytest.raises(APIError, match="rejected"):
        await match_receipt(client, "r1", "t1")
    assert client.gql_call.await_count == 2


async def test_match_requires_explicit_link_field():
    record = receipt()
    del record["orders"][0]["retailTransactions"][0]["transaction"]
    client = client_with({"retailSync": record})
    with pytest.raises(APIError):
        await match_receipt(client, "r1", "t1")
    assert client.gql_call.await_count == 1


async def test_match_transport_error_reports_uncertain_outcome():
    client = client_with({"retailSync": receipt()}, RuntimeError("connection closed"))
    client.get_transaction_details = AsyncMock(return_value={"getTransaction": {"id": "t1"}})
    with pytest.raises(APIError, match="before retrying"):
        await match_receipt(client, "r1", "t1")
    assert client.gql_call.await_count == 2
