"""Investment commands for Monarch CLI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner

app = typer.Typer(
    help="Investment holdings",
    no_args_is_help=True,
)


def _nested_value(data: dict[str, Any], key: str, nested_key: str) -> Any:
    """Read a nested value from an optional dictionary."""
    value = data.get(key)
    if isinstance(value, dict):
        return value.get(nested_key)
    return None


def _is_investment_account(account: dict[str, Any]) -> bool:
    """Check whether account metadata represents an investment account."""
    return bool(_nested_value(account, "type", "name") == "brokerage")


def _get_accounts_call(client: Any) -> Awaitable[dict[str, Any]]:
    """Call upstream get_accounts with an explicit type for mypy."""
    return cast(Awaitable[dict[str, Any]], client.get_accounts())


def _get_account_holdings_call(client: Any, account_id: int) -> Awaitable[dict[str, Any]]:
    """Call upstream get_account_holdings with an explicit type for mypy."""
    return cast(Awaitable[dict[str, Any]], client.get_account_holdings(account_id))


def _get_account_holdings_factory(
    client: Any,
    account_id: int,
) -> Callable[[], Awaitable[dict[str, Any]]]:
    """Create a holdings call factory with account_id bound for retries."""

    def call() -> Awaitable[dict[str, Any]]:
        return _get_account_holdings_call(client, account_id)

    return call


def _select_accounts(
    accounts: list[dict[str, Any]],
    *,
    account_ids: list[str] | None,
    include_hidden: bool,
) -> list[dict[str, Any]]:
    """Select accounts to query for holdings."""
    if account_ids:
        account_by_id = {str(account.get("id")): account for account in accounts}
        return [
            account_by_id.get(
                account_id,
                {
                    "id": account_id,
                    "displayName": account_id,
                    "institution": None,
                    "subtype": None,
                    "isHidden": None,
                },
            )
            for account_id in account_ids
        ]

    return [
        account
        for account in accounts
        if _is_investment_account(account)
        and (account.get("holdingsCount") or 0) > 0
        and (include_hidden or not account.get("isHidden"))
    ]


def _first_holding_info(node: dict[str, Any]) -> dict[str, Any]:
    """Return the first nested holdings object, normalizing API shape variance."""
    holdings = node.get("holdings")
    if isinstance(holdings, list) and holdings:
        first = holdings[0]
        return first if isinstance(first, dict) else {}
    if isinstance(holdings, dict):
        return holdings
    return {}


def _flatten_holdings(
    account: dict[str, Any],
    holdings_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flatten Monarch holdings API data into tabular rows."""
    edges = holdings_data.get("portfolio", {}).get("aggregateHoldings", {}).get("edges", [])

    rows = []
    for edge in edges:
        node = edge.get("node") or {}
        security = node.get("security") or {}
        holding_info = _first_holding_info(node)
        ticker = security.get("ticker") or holding_info.get("ticker")
        name = security.get("name") or holding_info.get("name")

        rows.append(
            {
                "account_id": str(account.get("id")),
                "account_name": account.get("displayName"),
                "institution": _nested_value(account, "institution", "name"),
                "subtype": _nested_value(account, "subtype", "display"),
                "ticker": ticker,
                "name": name,
                "quantity": node.get("quantity"),
                "basis": node.get("basis"),
                "total_value": node.get("totalValue"),
                "current_price": security.get("currentPrice"),
                "one_day_change_percent": security.get("oneDayChangePercent"),
                "last_synced_at": node.get("lastSyncedAt"),
            }
        )

    return rows


def _aggregate_holdings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate flattened holdings by ticker/name."""
    grouped: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    account_sets: dict[tuple[str | None, str | None], set[str]] = {}

    for row in rows:
        key = (row.get("ticker"), row.get("name"))
        item = grouped.setdefault(
            key,
            {
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "quantity": 0,
                "basis": 0,
                "total_value": 0,
                "accounts": 0,
            },
        )
        item["quantity"] += row.get("quantity") or 0
        item["basis"] += row.get("basis") or 0
        item["total_value"] += row.get("total_value") or 0
        account_sets.setdefault(key, set()).add(str(row.get("account_id")))

    for key, account_ids in account_sets.items():
        grouped[key]["accounts"] = len(account_ids)

    return sorted(grouped.values(), key=lambda item: item["total_value"], reverse=True)


@app.command("holdings")
@handle_errors
def holdings_cmd(
    account: Annotated[
        list[str] | None,
        typer.Option(
            "-a",
            "--account",
            help="Specific account ID(s) to query. Repeatable.",
        ),
    ] = None,
    include_hidden: Annotated[
        bool,
        typer.Option(
            "--include-hidden",
            help="Include hidden investment accounts when discovering accounts.",
        ),
    ] = False,
    aggregate: Annotated[
        bool,
        typer.Option(
            "--aggregate",
            help="Aggregate holdings across accounts by ticker/name.",
        ),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Output account-wrapped raw API responses.",
        ),
    ] = False,
    format: Annotated[
        OutputFormat | None,
        typer.Option(
            "-f",
            "--format",
            help="Output format (plain, json, table, csv, compact)",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (shortcut for --format json)",
        ),
    ] = False,
) -> None:
    """List investment holdings.

    Discovers visible investment accounts with holdings by default. Use
    --account to query specific account IDs, including hidden accounts.

    Examples:
        monarch investments holdings --json
        monarch investments holdings --format table
        monarch investments holdings --aggregate --json
        monarch investments holdings --account ACC123 --json
    """
    output_format = OutputFormat.JSON if json_output else format
    account_ids = list(account) if account else None

    with spinner("Fetching investment holdings..."):
        client = get_authenticated_client()
        accounts_data = run_api_call(lambda: _get_accounts_call(client))
        accounts = accounts_data.get("accounts", [])
        selected_accounts = _select_accounts(
            accounts,
            account_ids=account_ids,
            include_hidden=include_hidden,
        )

        raw_results = []
        rows = []
        for selected_account in selected_accounts:
            account_id = int(str(selected_account.get("id")))
            holdings_data = run_api_call(_get_account_holdings_factory(client, account_id))
            if raw:
                raw_results.append(
                    {
                        "account": selected_account,
                        "holdings": holdings_data,
                    }
                )
            else:
                rows.extend(_flatten_holdings(selected_account, holdings_data))

    if raw:
        output(raw_results, output_format)
        return

    data = _aggregate_holdings(rows) if aggregate else rows
    output(data, output_format)
