"""Budget commands for Monarch CLI."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner

app = typer.Typer(
    help=(
        "Budget management\n\nExamples:\n    monarch budgets list\n    monarch budgets list --json"
    ),
    no_args_is_help=False,
    invoke_without_command=True,
)


def _transform_budgets(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform raw budget API response to simplified format.

    The API returns monthlyAmountsByCategory with nested monthlyAmounts arrays.
    We extract the current month's data for each category.

    Args:
        raw_data: Raw API response from get_budgets()

    Returns:
        List of budget items with category_id, budgeted, spent, remaining
    """
    result = []
    budget_data = raw_data.get("budgetData", {})
    monthly_by_category = budget_data.get("monthlyAmountsByCategory", [])

    # Get current month in YYYY-MM-01 format to match API
    current_month = date.today().replace(day=1).isoformat()

    for category_data in monthly_by_category:
        category = category_data.get("category", {})
        category_id = category.get("id")
        monthly_amounts = category_data.get("monthlyAmounts", [])

        # Find current month's amounts
        current_amounts = None
        for amounts in monthly_amounts:
            if amounts.get("month") == current_month:
                current_amounts = amounts
                break

        # Fall back to first month if current not found
        if current_amounts is None and monthly_amounts:
            current_amounts = monthly_amounts[0]

        if current_amounts:
            budgeted = current_amounts.get("plannedCashFlowAmount", 0) or 0
            actual = current_amounts.get("actualAmount", 0) or 0
            remaining = current_amounts.get("remainingAmount", 0) or 0

            # Only include categories with budget or spending
            if budgeted != 0 or actual != 0:
                result.append(
                    {
                        "category_id": category_id,
                        "budgeted": budgeted,
                        "spent": abs(actual),  # Show as positive
                        "remaining": remaining,
                    }
                )

    return result


def _resolve_format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    """Resolve explicit output flags."""
    return OutputFormat.JSON if json_output else format


def _list_budgets(
    *,
    start: str | None,
    end: str | None,
    raw: bool,
    format: OutputFormat | None,
    json_output: bool,
) -> None:
    """Fetch and output budgets."""
    output_format = _resolve_format(format, json_output)

    with spinner("Fetching budgets..."):
        client = get_authenticated_client()
        if start is None and end is None:
            raw_data: dict[str, Any] = run_api_call(lambda: client.get_budgets())
        else:
            raw_data = run_api_call(lambda: client.get_budgets(start_date=start, end_date=end))
        data: Any = raw_data if raw else _transform_budgets(raw_data)

    output(data, output_format)


@app.callback()
@handle_errors
def main(
    ctx: typer.Context,
    start: Annotated[
        str | None,
        typer.Option("-s", "--start", help="Start date filter (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("-e", "--end", help="End date filter (YYYY-MM-DD)"),
    ] = None,
    raw: Annotated[bool, typer.Option("--raw", help="Output raw API response")] = False,
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
    """List budget status with spent/remaining amounts."""
    if ctx.invoked_subcommand is None:
        _list_budgets(start=start, end=end, raw=raw, format=format, json_output=json_output)


@app.command("list")
@handle_errors
def list_cmd(
    start: Annotated[
        str | None,
        typer.Option("-s", "--start", help="Start date filter (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("-e", "--end", help="End date filter (YYYY-MM-DD)"),
    ] = None,
    raw: Annotated[bool, typer.Option("--raw", help="Output raw API response")] = False,
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
    """List budget status with spent/remaining amounts.

    Shows all budget categories with their allocated amount, spending,
    and remaining balance. Spent amounts are shown as positive numbers.

    Examples:
        monarch budgets list                # Plain format (default in terminal)
        monarch budgets list --json         # JSON format
        monarch budgets list --format table # Table format
        monarch budgets list | jq .         # Auto-JSON when piped
        monarch budgets list | jq '[.[] | select(.remaining < 0)]'  # Over budget
    """
    _list_budgets(start=start, end=end, raw=raw, format=format, json_output=json_output)


@app.command("reset")
@handle_errors
def reset(
    start: Annotated[str | None, typer.Option("--start", help="Start date (YYYY-MM-DD)")] = None,
) -> None:
    """Reset budget data."""
    with spinner("Resetting budget..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.reset_budget(start_date=start))
    output(data)


@app.command("set")
@handle_errors
def set_amount(
    amount: Annotated[float, typer.Option("--amount", help="Budget amount")],
    category: Annotated[
        str | None,
        typer.Option("--category", help="Category ID to update"),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option("--group", help="Category group ID to update"),
    ] = None,
    timeframe: Annotated[str, typer.Option("--timeframe", help="Budget timeframe")] = "month",
    start: Annotated[str | None, typer.Option("--start", help="Start date (YYYY-MM-DD)")] = None,
    future: Annotated[bool, typer.Option("--future", help="Apply to future months")] = False,
) -> None:
    """Set a category or category-group budget amount."""
    if (category is None and group is None) or (category is not None and group is not None):
        output({"status": "error", "message": "Provide exactly one of --category or --group."})
        raise typer.Exit(1)

    with spinner("Updating budget amount..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.set_budget_amount(
                amount=amount,
                category_id=category,
                category_group_id=group,
                timeframe=timeframe,
                start_date=start,
                apply_to_future=future,
            )
        )
    output(data)


@app.command("flexible")
@handle_errors
def flexible(
    amount: Annotated[float, typer.Option("--amount", help="Flexible budget amount")],
    start: Annotated[str | None, typer.Option("--start", help="Start date (YYYY-MM-DD)")] = None,
    future: Annotated[bool, typer.Option("--future", help="Apply to future months")] = False,
) -> None:
    """Update flexible budget amount."""
    with spinner("Updating flexible budget..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.update_flexible_budget(
                amount=amount,
                start_date=start,
                apply_to_future=future,
            )
        )
    output(data)


@app.command("flex-rollover")
@handle_errors
def flex_rollover(
    start_month: Annotated[
        str | None,
        typer.Option("--start-month", help="Rollover start month (YYYY-MM-DD)"),
    ] = None,
    starting_balance: Annotated[
        float,
        typer.Option("--starting-balance", help="Starting rollover balance"),
    ] = 0.0,
    enabled: Annotated[
        bool,
        typer.Option("--enabled/--disabled", help="Enable or disable flex rollover"),
    ] = True,
    budget_system: Annotated[str, typer.Option("--budget-system", help="Budget system")] = (
        "fixed_and_flex"
    ),
) -> None:
    """Update flex rollover settings."""
    with spinner("Updating flex rollover settings..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.update_flex_rollover_settings(
                rollover_start_month=start_month,
                rollover_starting_balance=starting_balance,
                rollover_enabled=enabled,
                budget_system=budget_system,
            )
        )
    output(data)
