"""Read-only investment holdings orchestration."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from typing import Any, cast

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.exceptions import ValidationError
from ..core.operations import Effect, Operation, run_read_async_call, run_read_call
from ..transformers.investments import (
    transform_account_holdings,
    transform_investment_accounts,
)

HOLDINGS_OPERATION = Operation(
    command="investments holdings", effects=frozenset({Effect.READ_ONLY})
)
MAX_HOLDINGS_CONCURRENCY = 4


def _validate_account_id(account_id: str) -> str:
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValidationError(
            message="--account must be a non-empty opaque account ID.", field="account"
        )
    return account_id


def _normal_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return "".join(char for char in value.casefold() if char.isalnum()) or None


def _known_empty(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value == 0
    )


def account_is_holdings_eligible(account: Mapping[str, Any]) -> bool:
    """Return whether released account metadata supports holdings reads.

    Brokerage/investment subtypes are eligible for both linked brokerage
    accounts and manual investment accounts.  Manual accounts are accepted
    only when the released ``manualInvestmentsTrackingMethod`` explicitly
    indicates holdings/securities tracking; balance-only manual investments
    must not trigger a holdings request.
    """
    account_type = _normal_key(account.get("type"))
    subtype = _normal_key(account.get("subtype"))
    tracking = _normal_key(account.get("manual_tracking"))
    investment_names = {
        "brokerage",
        "investment",
        "investments",
        "retirement",
        "ira",
        "401k",
        "403b",
    }
    manual_holdings = {"holdings", "securities", "security", "investments"}
    if bool(account.get("is_manual")):
        return tracking in manual_holdings
    return account_type in investment_names or subtype in investment_names


def _select_accounts(
    accounts: list[dict[str, Any]],
    requested_ids: list[str] | None,
    include_hidden: bool,
) -> list[dict[str, Any]]:
    by_id = {
        str(account["id"]): account
        for account in accounts
        if isinstance(account.get("id"), str) and account["id"]
    }
    if requested_ids is not None:
        unknown = [account_id for account_id in requested_ids if account_id not in by_id]
        if unknown:
            raise ValidationError(
                message="One or more requested account IDs were not found.",
                field="account",
                details={"unknown_account_ids": unknown},
            )
        ineligible = [
            account_id
            for account_id in requested_ids
            if not account_is_holdings_eligible(by_id[account_id])
        ]
        if ineligible:
            raise ValidationError(
                message="One or more requested accounts are not holdings-eligible.",
                field="account",
                details={"ineligible_account_ids": ineligible},
            )
        selected = [by_id[account_id] for account_id in requested_ids]
    else:
        selected = [
            account
            for account in accounts
            if account_is_holdings_eligible(account)
            and (include_hidden or not account.get("is_hidden"))
        ]

    # A reported zero is authoritative for fanout selection. Missing counts
    # are unknown and remain eligible; the holdings read can return an empty
    # collection without us inventing a count.
    return sorted(
        [account for account in selected if not _known_empty(account.get("holdings_count"))],
        key=lambda account: str(account.get("id")),
    )


async def _fetch_holdings(
    client: Any,
    accounts: list[dict[str, Any]],
    operation: Operation,
) -> list[tuple[dict[str, Any], Any]]:
    semaphore = asyncio.Semaphore(MAX_HOLDINGS_CONCURRENCY)

    async def fetch(account: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        async with semaphore:
            account_id = cast(str, account["id"])
            raw = await run_read_async_call(
                lambda: cast(Any, client.get_account_holdings(account_id)), operation
            )
            return account, raw

    # gather propagates the first typed read error and the service returns no
    # partial result. Every task remains bounded by the shared executor.
    return list(await asyncio.gather(*(fetch(account) for account in accounts)))


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate only security-ID-keyed rows without monetary arithmetic."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    unkeyed: list[dict[str, Any]] = []
    for row in rows:
        security_id = row.get("security_id")
        if isinstance(security_id, str) and security_id:
            grouped.setdefault(security_id, []).append(row)
        else:
            unkeyed.append(row)

    result: list[dict[str, Any]] = []
    for security_id in sorted(grouped):
        members = sorted(
            grouped[security_id],
            key=lambda row: (str(row.get("account_id")), str(row.get("holding_id"))),
        )
        quantities = [row.get("quantity") for row in members]
        quantity = (
            sum(cast(list[int | float], quantities))
            if all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in quantities
            )
            else None
        )
        account_ids = sorted({str(row["account_id"]) for row in members})
        first = members[0]
        result.append(
            {
                "security_id": security_id,
                "ticker": first.get("ticker"),
                "name": first.get("name"),
                "security_type": first.get("security_type"),
                "security_type_display": first.get("security_type_display"),
                "quantity": quantity,
                "account_ids": account_ids,
                "account_count": len(account_ids),
                "account_contributions": [
                    {
                        "account_id": row.get("account_id"),
                        "account_name": row.get("account_name"),
                        "quantity": row.get("quantity"),
                        "basis": row.get("basis"),
                        "price": row.get("price"),
                        "total_value": row.get("total_value"),
                        "last_synced_at": row.get("last_synced_at"),
                    }
                    for row in members
                ],
            }
        )

    # Unkeyed rows are not grouped, preserving source context and all nulls.
    return result + sorted(
        unkeyed,
        key=lambda row: (str(row.get("account_id")), str(row.get("holding_id"))),
    )


def get_investment_holdings(
    account_ids: list[str] | None = None,
    *,
    include_hidden: bool = False,
    aggregate: bool = False,
    raw: bool = False,
    operation: Operation = HOLDINGS_OPERATION,
) -> list[dict[str, Any]] | dict[str, dict[str, Any]]:
    """Discover eligible accounts once and read holdings with bounded fanout."""
    requested: list[str] | None = None
    if account_ids is not None:
        requested = []
        for account_id in account_ids:
            validated = _validate_account_id(account_id)
            if validated not in requested:
                requested.append(validated)

    client = get_authenticated_client()
    discovery = run_read_call(lambda: client.get_accounts(), operation)
    accounts = transform_investment_accounts(discovery)
    selected = _select_accounts(accounts, requested, include_hidden)
    responses = run_async(_fetch_holdings(client, selected, operation))

    if raw:
        # Dict insertion order is stable after account-ID sorting; enclosed
        # values are the upstream responses without transformation.
        return {str(account["id"]): payload for account, payload in responses}

    rows: list[dict[str, Any]] = []
    for account, payload in responses:
        rows.extend(transform_account_holdings(payload, account))
    rows.sort(key=lambda row: (str(row.get("account_id")), str(row.get("holding_id"))))
    return _aggregate(rows) if aggregate else rows


__all__ = [
    "HOLDINGS_OPERATION",
    "MAX_HOLDINGS_CONCURRENCY",
    "account_is_holdings_eligible",
    "get_investment_holdings",
]
