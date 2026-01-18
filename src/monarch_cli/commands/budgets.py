"""Budget commands for Monarch CLI."""

from __future__ import annotations

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

    Args:
        raw_data: Raw API response from get_budgets()

    Returns:
        List of budget items with id, category, budgeted, spent, remaining
    """
    result = []
    budget_items = raw_data.get("budgetData", {}).get("budgetItems", [])

    for budget in budget_items:
        result.append(
            {
                "id": budget.get("id"),
                "category": budget.get("category", {}).get("name"),
                "budgeted": budget.get("budgetAmount"),
                "spent": abs(budget.get("spentAmount", 0)),  # Abs for readability
                "remaining": budget.get("remainingAmount"),
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
