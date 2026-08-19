"""Investment holding transformers and aggregation."""

from __future__ import annotations

from datetime import date
from typing import Any


def _round_optional(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _position(node: dict[str, Any], account: str, net_worth: float) -> dict[str, Any]:
    security = node.get("security") or {}
    holding = (node.get("holdings") or [{}])[0]
    ticker = security.get("ticker") or holding.get("ticker")
    name = security.get("name") or holding.get("name") or "Unknown"
    value = node.get("totalValue")
    basis = node.get("basis")
    gain = value - basis if value is not None and basis is not None else None
    return {
        "account": account,
        "ticker": ticker,
        "name": name,
        "quantity": node.get("quantity"),
        "price": (
            security.get("currentPrice")
            or security.get("closingPrice")
            or holding.get("closingPrice")
        ),
        "value": _round_optional(value),
        "basis": _round_optional(basis),
        "gain": _round_optional(gain),
        "gain_percent": round(gain / basis, 4) if gain is not None and basis else None,
        "pct_of_net_worth": round((value or 0) / net_worth, 4) if net_worth else None,
    }


def transform_holdings(
    accounts: list[dict[str, Any]],
    holdings_by_account: list[tuple[str, dict[str, Any]]],
    *,
    ticker: str | None = None,
    search: str | None = None,
    min_value: float | None = None,
) -> dict[str, Any]:
    """Flatten, filter, and aggregate investment holdings."""
    included = [account for account in accounts if account.get("includeBalanceInNetWorth", True)]
    net_worth = round(
        sum(float(account.get("currentBalance") or 0) for account in included),
        2,
    )

    positions = []
    for account_name, raw in holdings_by_account:
        edges = ((raw.get("portfolio") or {}).get("aggregateHoldings") or {}).get("edges") or []
        for edge in edges:
            position = _position(edge.get("node") or {}, account_name, net_worth)
            if not position["quantity"] and not position["value"]:
                continue
            if ticker and (position["ticker"] or "").casefold() != ticker.casefold():
                continue
            if search:
                term = search.casefold()
                if (
                    term not in (position["ticker"] or "").casefold()
                    and term not in (position["name"] or "").casefold()
                ):
                    continue
            if min_value is not None and (position["value"] or 0) < min_value:
                continue
            positions.append(position)
    securities: dict[str, dict[str, Any]] = {}
    security_basis_complete: dict[str, bool] = {}
    for position in positions:
        key = position["ticker"] or position["name"]
        security = securities.setdefault(
            key,
            {
                "ticker": position["ticker"],
                "name": position["name"],
                "quantity": 0.0,
                "value": 0.0,
                "basis": 0.0,
                "accounts": [],
            },
        )
        security_basis_complete.setdefault(key, True)
        security["quantity"] += position["quantity"] or 0
        security["value"] += position["value"] or 0
        if position["basis"] is None:
            security_basis_complete[key] = False
        else:
            security["basis"] += position["basis"]
        if position["account"] not in security["accounts"]:
            security["accounts"].append(position["account"])

    by_security = []
    for key, security in securities.items():
        basis = round(security["basis"], 2) if security_basis_complete[key] else None
        value = round(security["value"], 2)
        by_security.append(
            {
                "ticker": security["ticker"],
                "name": security["name"],
                "quantity": round(security["quantity"], 4),
                "value": value,
                "basis": basis,
                "gain": round(value - basis, 2) if basis is not None else None,
                "pct_of_net_worth": round(value / net_worth, 4) if net_worth else None,
                "accounts": security["accounts"],
            }
        )
    by_security.sort(key=lambda security: security["value"], reverse=True)
    positions.sort(key=lambda position: position["value"] or 0, reverse=True)

    total_value = round(sum(position["value"] or 0 for position in positions), 2)
    basis_complete = all(position["basis"] is not None for position in positions)
    total_basis = (
        round(sum(position["basis"] or 0 for position in positions), 2) if basis_complete else None
    )
    return {
        "as_of": date.today().isoformat(),
        "net_worth": net_worth,
        "filtered": bool(ticker or search or min_value is not None),
        "totals": {
            "value": total_value,
            "basis": total_basis,
            "gain": round(total_value - total_basis, 2) if total_basis is not None else None,
            "pct_of_net_worth": round(total_value / net_worth, 4) if net_worth else None,
        },
        "by_security": by_security,
        "positions": positions,
    }
