"""Investment holdings command."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner
from ..transformers.holdings import transform_holdings

app = typer.Typer(help="Investment holdings and concentration", no_args_is_help=False)


@app.command("list")
@handle_errors
def list_cmd(
    ticker: Annotated[
        str | None,
        typer.Option("--ticker", help="Exact ticker symbol"),
    ] = None,
    search: Annotated[
        str | None,
        typer.Option("--search", help="Security name or ticker substring"),
    ] = None,
    account: Annotated[
        str | None,
        typer.Option("--account", help="Account name substring"),
    ] = None,
    min_value: Annotated[
        float | None,
        typer.Option("--min-value", min=0, help="Minimum position value"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List per-account positions and aggregate them by security."""
    with spinner("Fetching investment holdings..."):
        client = get_authenticated_client()
        account_data: dict[str, Any] = run_api_call(lambda: client.get_accounts())
        accounts = account_data.get("accounts", [])
        investment_accounts = [
            item
            for item in accounts
            if str((item.get("type") or {}).get("name", "")).casefold() == "brokerage"
            and (not account or account.casefold() in str(item.get("displayName", "")).casefold())
        ]

        async def fetch_all() -> list[tuple[str, dict[str, Any]]]:
            responses = await asyncio.gather(
                *(client.get_account_holdings(item["id"]) for item in investment_accounts)
            )
            return [
                (str(item.get("displayName") or item["id"]), response)
                for item, response in zip(investment_accounts, responses, strict=True)
            ]

        holdings_by_account = run_api_call(fetch_all)

    result = transform_holdings(
        accounts,
        holdings_by_account,
        ticker=ticker,
        search=search,
        min_value=min_value,
    )
    result["filtered"] = bool(ticker or search or account or min_value is not None)
    output(result, OutputFormat.JSON if json_output else format)
