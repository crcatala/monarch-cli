"""Normalizers for the released investment holdings API shapes.

The upstream holdings response is account-scoped but does not identify the
account in each aggregate node.  The service supplies that request context to
these transformers, which never calculate monetary values or replace missing
numbers with sentinels.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .nesting import bool_or_default, list_or_empty, nested_get, require_object

HOLDINGS_RECORD_FIELDS: tuple[str, ...] = (
    "account_id",
    "account_name",
    "security_id",
    "holding_id",
    "ticker",
    "name",
    "security_type",
    "security_type_display",
    "quantity",
    "basis",
    "price",
    "total_value",
    "last_synced_at",
)


def transform_investment_accounts(raw: Any) -> list[dict[str, Any]]:
    """Normalize discovery metadata needed for holdings selection.

    ``holdingsCount`` is retained only for selection; it is not a financial
    value.  Missing counts remain ``None`` so the service skips only accounts
    that the upstream explicitly reports as empty.
    """
    response = require_object(raw, "investment account discovery")
    accounts = list_or_empty(response.get("accounts"))
    result: list[dict[str, Any]] = []
    for account in accounts:
        if not isinstance(account, Mapping):
            continue
        result.append(
            {
                "id": nested_get(account, "id"),
                "name": nested_get(account, "displayName"),
                "type": nested_get(account, "type", "name"),
                "subtype": nested_get(account, "subtype", "name"),
                "is_hidden": bool_or_default(nested_get(account, "isHidden"), False),
                "is_manual": bool_or_default(nested_get(account, "isManual"), False),
                "holdings_count": nested_get(account, "holdingsCount"),
                "manual_tracking": nested_get(account, "manualInvestmentsTrackingMethod"),
            }
        )
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_security_description(node: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the first descriptive holding node, if the list is usable."""
    holdings = node.get("holdings")
    if isinstance(holdings, list):
        for item in holdings:
            if isinstance(item, Mapping):
                return item
    if isinstance(holdings, Mapping):
        return holdings
    return {}


def _number_or_none(value: Any) -> int | float | None:
    """Keep finite numeric upstream values and preserve unavailable values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _preferred(value: Any, fallback: Any) -> Any:
    return value if value is not None else fallback


def transform_account_holdings(raw: Any, account: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize one account's aggregate holdings into deterministic rows.

    The released client returns ``portfolio.aggregateHoldings.edges``.  A
    missing/null portfolio, aggregate container, or edge list means no rows;
    malformed top-level responses still raise a typed API error.
    """
    response = require_object(raw, "account holdings")
    portfolio = _mapping(response.get("portfolio"))
    aggregate = _mapping(portfolio.get("aggregateHoldings"))
    edges = list_or_empty(aggregate.get("edges"))
    rows: list[dict[str, Any]] = []

    for edge in edges:
        node = _mapping(edge).get("node") if isinstance(edge, Mapping) else None
        node_mapping = _mapping(node)
        security = _mapping(node_mapping.get("security"))
        description = _first_security_description(node_mapping)
        rows.append(
            {
                "account_id": account.get("id"),
                "account_name": account.get("name"),
                "security_id": security.get("id"),
                "holding_id": node_mapping.get("id"),
                "ticker": _preferred(security.get("ticker"), description.get("ticker")),
                "name": _preferred(security.get("name"), description.get("name")),
                "security_type": _preferred(security.get("type"), description.get("type")),
                "security_type_display": _preferred(
                    security.get("typeDisplay"), description.get("typeDisplay")
                ),
                "quantity": _number_or_none(node_mapping.get("quantity")),
                "basis": _number_or_none(node_mapping.get("basis")),
                "price": _number_or_none(
                    _preferred(security.get("currentPrice"), security.get("closingPrice"))
                ),
                "total_value": _number_or_none(node_mapping.get("totalValue")),
                "last_synced_at": node_mapping.get("lastSyncedAt"),
            }
        )
    return rows


__all__ = ["HOLDINGS_RECORD_FIELDS", "transform_account_holdings", "transform_investment_accounts"]
