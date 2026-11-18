"""Native saved-report management, separate from cashflow data exports."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, NetworkError, ValidationError
from ..core.report_api import create_report, delete_report, list_reports, rename_report, show_report
from ..core.report_config import build_create_input, clean_name
from ..output import OutputFormat, output

app = typer.Typer(
    help="List, create, rename, and delete saved Monarch reports", no_args_is_help=True
)


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"Duplicate JSON configuration key: {key}")
        result[key] = value
    return result


def _read_object(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_unique_keys)
    except (ValueError, OSError) as exc:
        raise ValidationError(f"Cannot read JSON configuration: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Report configuration files must contain a JSON object")
    return value


def _write(factory: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return run_api_call(factory, max_retries=0)
    except NetworkError as exc:
        raise APIError(
            "Report request failed; inspect report list before retrying. "
            "A submitted write may have completed.",
            details={"cause": str(exc)},
        ) from exc


@app.command("list")
@handle_errors
def list_saved(
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List all saved report configurations, including filters and chart settings."""
    client = get_authenticated_client()
    data = run_api_call(lambda: list_reports(client))
    output(data, OutputFormat.JSON if json_output else format)


@app.command("show")
@handle_errors
def show(
    report_id: Annotated[str, typer.Argument(help="Saved report ID from report list")],
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect one saved report by exact ID."""
    client = get_authenticated_client()
    data = run_api_call(lambda: show_report(client, report_id))
    output(data, OutputFormat.JSON if json_output else format)


@app.command("create")
@handle_errors
def create(
    name: Annotated[str, typer.Option("--name", help="Saved report name")],
    url: Annotated[
        str | None, typer.Option("--url", help="Monarch cash-flow, spending, or income URL")
    ] = None,
    filters_file: Annotated[
        Path | None, typer.Option("--filters-file", exists=True, dir_okay=False, readable=True)
    ] = None,
    view_file: Annotated[
        Path | None, typer.Option("--view-file", exists=True, dir_okay=False, readable=True)
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate and preview input without authentication")
    ] = False,
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Save a report from a URL or JSON configuration; defaults to cash-flow Sankey.

    This saves a view in Monarch. It does not export a chart or change transactions.
    Unsupported URL settings are rejected, not silently discarded.
    """
    spec = build_create_input(
        name, url=url, filters=_read_object(filters_file), view=_read_object(view_file)
    )
    client = None if dry_run else get_authenticated_client()
    data = _write(lambda: create_report(client, spec, dry_run=dry_run))
    output(data, OutputFormat.JSON if json_output else format)


@app.command("rename")
@handle_errors
def rename(
    report_id: Annotated[str, typer.Argument(help="Saved report ID from report list")],
    name: Annotated[str, typer.Option("--name", help="New saved report name")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Read and preview without writing")
    ] = False,
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Rename a saved report and verify that its filters and view remain unchanged."""
    name = clean_name(name)
    client = get_authenticated_client()
    data = _write(lambda: rename_report(client, report_id, name, dry_run=dry_run))
    output(data, OutputFormat.JSON if json_output else format)


@app.command("delete")
@handle_errors
def delete(
    report_id: Annotated[str, typer.Argument(help="Saved report ID from report list")],
    yes: Annotated[
        bool, typer.Option("--yes", help="Confirm deletion of this saved report")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Read and preview without deleting")
    ] = False,
    format: Annotated[OutputFormat | None, typer.Option("--format", "-f")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete one saved report and verify its absence; requires --yes or --dry-run."""
    if not yes and not dry_run:
        raise ValidationError("Report deletion requires --yes; use --dry-run to preview")
    client = get_authenticated_client()
    data = _write(lambda: delete_report(client, report_id, dry_run=dry_run))
    output(data, OutputFormat.JSON if json_output else format)
