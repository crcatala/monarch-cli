"""Categories commands for Monarch CLI."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..output import OutputFormat, output
from ..output.progress import spinner

app = typer.Typer(
    help=(
        "Category management\n\nExamples:\n"
        "    monarch categories list\n"
        "    monarch categories list --json"
    ),
    no_args_is_help=False,
    invoke_without_command=True,
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


def _resolve_format(format: OutputFormat | None, json_output: bool) -> OutputFormat | None:
    """Resolve explicit output flags."""
    return OutputFormat.JSON if json_output else format


def _list_categories(format: OutputFormat | None, json_output: bool) -> None:
    """Fetch and output categories."""
    output_format = _resolve_format(format, json_output)
    with spinner("Fetching categories..."):
        client = get_authenticated_client()
        raw_data: dict[str, Any] = run_api_call(lambda: client.get_transaction_categories())
        data = _transform_categories(raw_data)
    output(data, output_format)


@app.callback()
@handle_errors
def main(
    ctx: typer.Context,
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
    """List all transaction categories."""
    if ctx.invoked_subcommand is None:
        _list_categories(format, json_output)


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
    _list_categories(format, json_output)


@app.command("groups")
@handle_errors
def groups(
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List category groups."""
    with spinner("Fetching category groups..."):
        client = get_authenticated_client()
        data: Any = run_api_call(lambda: client.get_transaction_category_groups())
    output(data, _resolve_format(format, json_output))


@app.command("create")
@handle_errors
def create(
    group: Annotated[str, typer.Option("--group", help="Category group ID")],
    name: Annotated[str, typer.Option("--name", help="Category name")],
    icon: Annotated[str, typer.Option("--icon", help="Category icon")] = "?",
    rollover_enabled: Annotated[
        bool,
        typer.Option("--rollover-enabled/--rollover-disabled"),
    ] = False,
    rollover_type: Annotated[str, typer.Option("--rollover-type", help="Rollover type")] = (
        "monthly"
    ),
    rollover_start: Annotated[
        str | None,
        typer.Option("--rollover-start", help="Rollover start month/date (YYYY-MM-DD)"),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("-f", "--format", help="Output format (plain, json, table, csv, compact)"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a transaction category."""
    start_month = datetime.fromisoformat(rollover_start) if rollover_start else datetime.now()
    with spinner("Creating category..."):
        client = get_authenticated_client()
        data: Any = run_api_call(
            lambda: client.create_transaction_category(
                group_id=group,
                transaction_category_name=name,
                rollover_start_month=start_month,
                icon=icon,
                rollover_enabled=rollover_enabled,
                rollover_type=rollover_type,
            )
        )
    output(data, _resolve_format(format, json_output))


@app.command("delete")
@handle_errors
def delete(
    category_ids: Annotated[list[str], typer.Argument(help="Category ID(s) to delete")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm category deletion")] = False,
) -> None:
    """Delete one or more categories."""
    if not yes:
        output({"status": "error", "message": "Category delete requires --yes."})
        raise typer.Exit(1)

    with spinner("Deleting categories..."):
        client = get_authenticated_client()
        if len(category_ids) == 1:
            data: Any = run_api_call(lambda: client.delete_transaction_category(category_ids[0]))
        else:
            data = run_api_call(lambda: client.delete_transaction_categories(category_ids))
    output({"status": "deleted", "category_ids": category_ids, "result": data})
