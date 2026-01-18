"""Budget commands for Monarch CLI."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner

app = typer.Typer(
    help="Budget management",
    no_args_is_help=True,
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


@app.command("list")
@handle_errors
def list_cmd(
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
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching budgets..."):
        client = get_authenticated_client()
        raw_data: dict[str, Any] = run_async(client.get_budgets())

        # Transform to simplified format
        data = _transform_budgets(raw_data)

    output(data, output_format)
