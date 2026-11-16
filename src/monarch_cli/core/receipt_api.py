"""Scanned receipt inbox and explicit matching through Monarch's private API."""

from typing import Any

from .exceptions import APIError, NotFoundError, ValidationError
from .receipt_queries import INBOX_QUERY, MATCH_MUTATION, RECEIPT_QUERY

RECEIPT_VENDORS = ("user_import", "email_import")


def _object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise APIError(f"Missing or invalid {description} in Monarch response")
    return value


def _records(value: Any, description: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise APIError(f"Missing or invalid {description} in Monarch response")
    return value


async def fetch_inbox(
    client: Any,
    *,
    limit: int = 25,
    offset: int = 0,
    status: str | None = None,
    order_by: str = "receipt_date",
) -> dict[str, Any]:
    """Fetch one server-filtered page, keeping receipt details in the API's field names."""
    filters: dict[str, Any] = {"vendors": list(RECEIPT_VENDORS)}
    if status is not None:
        filters["status"] = status
    data = _object(
        await client.gql_call(
            operation="Common_RetailSyncsQueryWithTotal",
            graphql_query=INBOX_QUERY,
            variables={
                "filters": filters,
                "offset": offset,
                "limit": limit,
                "includeTotalCount": True,
                "orderBy": order_by,
            },
        ),
        "receipt inbox",
    )
    page = _object(data.get("retailSyncsWithTotal"), "receipt page")
    results = _records(page.get("results"), "receipt results")
    total = page.get("totalCount")
    if type(total) is not int or total < 0 or len(results) > limit:
        raise APIError("Invalid receipt total or page size")
    if any(not row.get("id") or row.get("vendor") not in RECEIPT_VENDORS for row in results):
        raise APIError("Receipt inbox returned an invalid ID or unexpected vendor")
    if not results and offset < total:
        raise APIError("Receipt page is empty before totalCount; refusing incomplete pagination")
    next_offset = offset + len(results)
    return {
        "results": results,
        "total_count": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset if next_offset < total else None,
    }


async def fetch_receipt(client: Any, receipt_id: str) -> dict[str, Any]:
    """Fetch one scanned receipt, including status, line items, and linked transactions."""
    data = _object(
        await client.gql_call(
            operation="Common_RetailSyncQuery",
            graphql_query=RECEIPT_QUERY,
            variables={"syncId": receipt_id},
        ),
        "receipt detail",
    )
    if "retailSync" in data and data["retailSync"] is None:
        raise NotFoundError("Scanned receipt not found", resource_id=receipt_id)
    receipt = _object(data.get("retailSync"), "receipt detail")
    if receipt.get("id") != receipt_id or receipt.get("vendor") not in RECEIPT_VENDORS:
        raise APIError("Receipt detail returned a different ID or a non-receipt vendor")
    return receipt


def _select_transaction(
    receipt: dict[str, Any], retail_transaction_id: str | None
) -> dict[str, Any]:
    orders = _records(receipt.get("orders"), "receipt orders")
    transactions = [
        row
        for order in orders
        for row in _records(order.get("retailTransactions"), "retail transactions")
    ]
    if any(not isinstance(row.get("id"), str) or not row["id"] for row in transactions):
        raise APIError("Receipt contains an invalid retail transaction ID")
    if retail_transaction_id is not None:
        selected = [row for row in transactions if row["id"] == retail_transaction_id]
    else:
        selected = transactions
    if len(selected) != 1:
        raise ValidationError(
            "Select exactly one receipt retail transaction with --retail-transaction. "
            "Use receipts show to inspect IDs.",
            details={"retail_transaction_ids": [row["id"] for row in transactions]},
        )
    return selected[0]


async def match_receipt(
    client: Any,
    receipt_id: str,
    transaction_id: str,
    *,
    retail_transaction_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate both targets, match once, then verify the exact retail transaction link."""
    receipt = await fetch_receipt(client, receipt_id)
    if receipt.get("status") not in ("completed", "pending_matches"):
        raise ValidationError("Receipt is not ready for matching; inspect its processing status")
    selected = _select_transaction(receipt, retail_transaction_id)
    retail_id = selected["id"]
    result: dict[str, Any] = {
        "entity": "receipt_match",
        "id": receipt_id,
        "receipt_id": receipt_id,
        "retail_transaction_id": retail_id,
        "transaction_id": transaction_id,
    }
    if "transaction" not in selected:
        raise APIError("Receipt is missing its transaction link field")
    linked = selected["transaction"]
    if linked is not None:
        current = _object(linked, "linked transaction")
        if current.get("id") == transaction_id:
            return {**result, "status": "already_matched", "verified": True}
        raise ValidationError("Receipt retail transaction is already linked to another transaction")

    target_data = _object(
        await client.get_transaction_details(transaction_id=transaction_id, redirect_posted=False),
        "target transaction response",
    )
    if target_data.get("getTransaction") is None:
        raise NotFoundError("Target transaction not found", resource_id=transaction_id)
    target = _object(target_data["getTransaction"], "target transaction")
    if target.get("id") != transaction_id:
        raise APIError(
            "Target transaction ID changed; inspect the posted transaction before matching"
        )
    if dry_run:
        return {
            **result,
            "status": "dry_run",
            "receipt": receipt,
            "transaction": target,
            "message": "Matching can update notes, categories, and splits under Monarch settings",
        }

    try:
        response = await client.gql_call(
            operation="Common_MatchRetailTransaction",
            graphql_query=MATCH_MUTATION,
            variables={"retailTransactionId": retail_id, "transactionId": transaction_id},
        )
    except Exception as exc:
        raise APIError(
            "Match request failed; inspect receipts show before retrying. "
            "A submitted match may have completed.",
            details={**result, "cause": str(exc)},
        ) from exc
    data = _object(response, "receipt match response")
    payload = _object(data.get("matchRetailTransaction"), "receipt match payload")
    if payload.get("errors") is not None:
        raise APIError("Monarch rejected receipt matching", details={"errors": payload["errors"]})
    if (
        "errors" not in payload
        or _object(payload.get("retailSync"), "matched receipt").get("id") != receipt_id
    ):
        raise APIError("Invalid match response; inspect the receipt before retrying")
    try:
        after = await fetch_receipt(client, receipt_id)
        verified = _select_transaction(after, retail_id).get("transaction")
        if not isinstance(verified, dict) or verified.get("id") != transaction_id:
            raise APIError("Receipt link did not match the requested transaction")
    except Exception as exc:
        raise APIError(
            "Match submitted but could not verify its link; inspect receipts show before retrying",
            details={**result, "verification_error": str(exc)},
        ) from exc
    return {**result, "status": "matched", "verified": True, "result": after}
