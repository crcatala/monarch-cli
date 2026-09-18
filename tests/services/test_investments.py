"""Mock-only tests for bounded holdings orchestration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monarch_cli.core.exceptions import APIError, ValidationError
from monarch_cli.services.investments import (
    MAX_HOLDINGS_CONCURRENCY,
    get_investment_holdings,
)


def account(account_id: str, *, hidden: bool = False, count: int | None = 1) -> dict:
    return {
        "id": account_id,
        "displayName": f"Account {account_id}",
        "type": {"name": "brokerage"},
        "subtype": {"name": "taxable"},
        "isHidden": hidden,
        "isManual": False,
        "holdingsCount": count,
    }


def response(account_id: str, *, security_id: str | None = "security-1", quantity=2) -> dict:
    security = {"id": security_id, "ticker": "ABC", "name": "Alpha", "currentPrice": 5}
    return {
        "portfolio": {
            "aggregateHoldings": {
                "edges": [
                    {
                        "node": {
                            "id": f"node-{account_id}",
                            "quantity": quantity,
                            "basis": 7,
                            "totalValue": 10,
                            "security": security,
                        }
                    }
                ]
            }
        }
    }


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


def test_discovery_once_hidden_and_zero_accounts_are_not_read(client: MagicMock) -> None:
    client.get_account_holdings = AsyncMock(return_value=response("visible"))
    discovery = {
        "accounts": [account("visible"), account("hidden", hidden=True), account("empty", count=0)]
    }
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch("monarch_cli.services.investments.run_read_call", return_value=discovery) as read,
    ):
        result = get_investment_holdings()
    assert result[0]["account_id"] == "visible"
    read.assert_called_once()
    client.get_account_holdings.assert_awaited_once_with("visible")


def test_discovery_accounts_without_usable_ids_are_not_read(client: MagicMock) -> None:
    client.get_account_holdings = AsyncMock(return_value=response("missing"))
    missing_id = {**account("missing"), "id": None}
    whitespace_id = {**account("whitespace"), "id": "   "}
    discovery = {"accounts": [missing_id, whitespace_id]}
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch("monarch_cli.services.investments.run_read_call", return_value=discovery),
    ):
        assert get_investment_holdings() == []
    client.get_account_holdings.assert_not_awaited()


def test_manual_balance_only_account_is_ineligible() -> None:
    from monarch_cli.services.investments import account_is_holdings_eligible

    assert not account_is_holdings_eligible(
        {
            "type": "other_asset",
            "subtype": "investment",
            "is_manual": True,
            "manual_tracking": "balance",
        }
    )


def test_explicit_ids_validate_unknown_and_ineligible(client: MagicMock) -> None:
    discovery = {
        "accounts": [account("known"), {**account("checking"), "type": {"name": "depository"}}]
    }
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch("monarch_cli.services.investments.run_read_call", return_value=discovery),
    ):
        with pytest.raises(ValidationError, match="not found"):
            get_investment_holdings(["missing"])
        with pytest.raises(ValidationError, match="not holdings-eligible"):
            get_investment_holdings(["checking"])
    client.get_account_holdings.assert_not_called()


def test_explicit_hidden_account_is_allowed(client: MagicMock) -> None:
    client.get_account_holdings = AsyncMock(return_value=response("hidden"))
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch(
            "monarch_cli.services.investments.run_read_call",
            return_value={"accounts": [account("hidden", hidden=True)]},
        ),
    ):
        result = get_investment_holdings(["hidden"])
    assert result[0]["account_id"] == "hidden"
    client.get_account_holdings.assert_awaited_once_with("hidden")


def test_raw_is_deterministic_account_keyed_and_untouched(client: MagicMock) -> None:
    raw_a = {"future": None, "portfolio": {"x": 1}}
    client.get_account_holdings = AsyncMock(side_effect=[raw_a, {"portfolio": None}])
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch(
            "monarch_cli.services.investments.run_read_call",
            return_value={"accounts": [account("b"), account("a")]},
        ),
    ):
        result = get_investment_holdings(raw=True)
    assert list(result) == ["a", "b"]
    assert result["a"] is raw_a


def test_any_selected_failure_returns_no_partial_result(client: MagicMock) -> None:
    client.get_account_holdings = AsyncMock(side_effect=[response("a"), APIError("failed")])
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch(
            "monarch_cli.services.investments.run_read_call",
            return_value={"accounts": [account("a"), account("b")]},
        ),
        pytest.raises(APIError),
    ):
        get_investment_holdings()


def test_fanout_never_exceeds_four_calls(client: MagicMock) -> None:
    active = 0
    maximum = 0

    async def hold(account_id: str) -> dict:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return response(account_id)

    client.get_account_holdings.side_effect = hold
    discovery = {"accounts": [account(str(index)) for index in range(MAX_HOLDINGS_CONCURRENCY + 2)]}
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch("monarch_cli.services.investments.run_read_call", return_value=discovery),
    ):
        result = get_investment_holdings()
    assert len(result) == MAX_HOLDINGS_CONCURRENCY + 2
    assert maximum <= MAX_HOLDINGS_CONCURRENCY


def test_aggregate_security_id_only_and_no_cross_account_money(client: MagicMock) -> None:
    client.get_account_holdings = AsyncMock(
        side_effect=[response("a"), response("b"), response("c", security_id=None)]
    )
    with (
        patch("monarch_cli.services.investments.get_authenticated_client", return_value=client),
        patch(
            "monarch_cli.services.investments.run_read_call",
            return_value={"accounts": [account("a"), account("b"), account("c")]},
        ),
    ):
        result = get_investment_holdings(aggregate=True)
    grouped = result[0]
    assert grouped["security_id"] == "security-1"
    assert grouped["quantity"] == 4
    assert grouped["account_ids"] == ["a", "b"]
    assert grouped["account_count"] == 2
    assert "basis" not in grouped and "price" not in grouped and "total_value" not in grouped
    assert result[1]["security_id"] is None
    assert result[1]["account_id"] == "c"
