"""Net-worth transformer."""

from __future__ import annotations

from typing import Any


def transform_net_worth(raw: dict[str, Any]) -> dict[str, float | int]:
    """Compute net worth from accounts included by Monarch."""
    accounts = [
        account
        for account in raw.get("accounts", [])
        if account.get("includeBalanceInNetWorth", True)
    ]
    assets = sum(
        float(account.get("currentBalance") or 0) for account in accounts if account.get("isAsset")
    )
    signed_liabilities = sum(
        float(account.get("currentBalance") or 0)
        for account in accounts
        if not account.get("isAsset")
    )
    return {
        "net_worth": round(assets + signed_liabilities, 2),
        "total_assets": round(assets, 2),
        "total_liabilities": round(abs(signed_liabilities), 2),
        "account_count": len(accounts),
    }
