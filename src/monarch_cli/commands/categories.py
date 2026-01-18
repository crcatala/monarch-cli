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


def _transform_categories(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform category response to simplified list.

    The API returns categories with nested group objects:
    {
        "categories": [
            {
                "id": "...",
                "name": "Groceries",
                "icon": "...",
                "group": {"id": "...", "name": "Food", "type": "expense"}
            }
        ]
    }

    This transforms to:
    [{"id": "...", "name": "Groceries", "group": "Food", "icon": "..."}]

    Args:
        raw_data: Raw API response from get_transaction_categories()

    Returns:
        List of categories with id, name, group, icon
    """
    result = []
    categories = raw_data.get("categories", [])

    for category in categories:
        group = category.get("group", {})
        result.append(
            {
                "id": category.get("id"),
                "name": category.get("name"),
                "group": group.get("name") if group else None,
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

        # Transform to simplified structure
        data = _transform_categories(raw_data)

    output(data, output_format)
