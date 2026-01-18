"""Categories commands for Monarch CLI."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_async
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner

app = typer.Typer(
    help="Category management",
    no_args_is_help=True,
)


def _flatten_categories(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten nested category response to list of categories.

    The API returns categories nested under groups:
    {
        "categories": [
            {"name": "Food", "children": [{"id": "...", "name": "Groceries", "icon": "..."}]}
        ]
    }

    This flattens to:
    [{"id": "...", "name": "Groceries", "group": "Food", "icon": "..."}]

    Args:
        raw_data: Raw API response from get_transaction_categories()

    Returns:
        Flat list of categories with id, name, group, icon
    """
    result = []
    categories = raw_data.get("categories", [])

    for group in categories:
        group_name = group.get("name")
        children = group.get("children", [])

        for category in children:
            result.append(
                {
                    "id": category.get("id"),
                    "name": category.get("name"),
                    "group": group_name,
                    "icon": category.get("icon"),
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
    """List all transaction categories.

    Shows all categories organized by their group (e.g., Food, Transportation).
    Output includes id, name, group, and icon for each category.

    Examples:
        monarch categories list                # Plain format (default in terminal)
        monarch categories list --json         # JSON format
        monarch categories list --format table # Table format
        monarch categories list | jq .         # Auto-JSON when piped
        monarch categories list | jq '[.[] | select(.group == "Food")]'  # Filter by group
    """
    # Determine output format
    output_format = format
    if json_output:
        output_format = OutputFormat.JSON

    with spinner("Fetching categories..."):
        client = get_authenticated_client()
        raw_data: dict[str, Any] = run_async(client.get_transaction_categories())

        # Flatten nested structure
        data = _flatten_categories(raw_data)

    output(data, output_format)
