"""
Full output system for monarch-cli.

Supports multiple output formats:
- JSON (pretty, indented)
- COMPACT (single-line JSON)
- TABLE (Rich table for human reading)
- CSV (spreadsheet export)
- NDJSON (streaming, one JSON object per line)
"""

import csv
import json
import sys
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table

from ..core.exceptions import MonarchCLIError


class OutputFormat(str, Enum):
    """Output format options."""

    JSON = "json"
    TABLE = "table"
    CSV = "csv"
    COMPACT = "compact"


# Rich console for styled interactive output (uses stderr to keep stdout clean)
console = Console(stderr=True)

# Console for stdout (used for table output)
_stdout_console = Console()

# Module-level verbose flag
_verbose = False


def set_verbose(v: bool) -> None:
    """Set the verbose output flag."""
    global _verbose
    _verbose = v


def is_verbose() -> bool:
    """Check if verbose output is enabled."""
    return _verbose


def is_interactive() -> bool:
    """Check if stdout is a TTY (interactive terminal).

    Returns:
        True if stdout is connected to a terminal, False if piped/redirected.
    """
    return sys.stdout.isatty()


def print_table(items: list[dict[str, Any]]) -> None:
    """Print a list of dicts as a Rich table.

    Args:
        items: List of dictionaries to display. All dicts should have same keys.

    Note:
        Handles empty list gracefully with a dim "No results" message.
    """
    if not items:
        _stdout_console.print("[dim]No results[/dim]")
        return

    # Get column names from first item
    columns = list(items[0].keys())

    table = Table()
    for col in columns:
        table.add_column(col)

    for item in items:
        row = [str(item.get(col, "")) for col in columns]
        table.add_row(*row)

    _stdout_console.print(table)


def print_csv(items: list[dict[str, Any]]) -> None:
    """Print a list of dicts as CSV to stdout.

    Args:
        items: List of dictionaries to output. All dicts should have same keys.

    Note:
        Handles empty list gracefully (outputs nothing).
    """
    if not items:
        return

    # Get fieldnames from first item
    fieldnames = list(items[0].keys())

    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(items)


def output(
    data: Any,
    format: OutputFormat = OutputFormat.JSON,
    ndjson: bool = False,
    raw: bool = False,
) -> None:
    """Output data in specified format.

    Args:
        data: Data to output.
        format: Output format (JSON, TABLE, CSV, COMPACT).
        ndjson: If True and data is a list, print each item as single-line JSON.
        raw: If True, print data as-is (pass-through).

    Note:
        TABLE and CSV only work with list[dict] data.
        For non-list data, these formats fall back to JSON.
    """
    # Raw pass-through
    if raw:
        print(data)
        return

    # NDJSON streaming for lists
    if ndjson and isinstance(data, list):
        for item in data:
            print(json.dumps(item, default=str))
        return

    # Format-specific output
    if format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))

    elif format == OutputFormat.TABLE:
        # TABLE only works for list of dicts
        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            print_table(data)
        else:
            # Fall back to JSON for non-list data
            print(json.dumps(data, indent=2, default=str))

    elif format == OutputFormat.CSV:
        # CSV only works for list of dicts
        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            print_csv(data)
        else:
            # Fall back to JSON for non-list data
            print(json.dumps(data, indent=2, default=str))

    else:
        # Default: JSON with indent
        print(json.dumps(data, indent=2, default=str))


def output_error(error: MonarchCLIError) -> None:
    """Output structured error for AI agent consumption.

    Outputs error as JSON to stderr for consistent machine-readable output.

    Args:
        error: MonarchCLIError instance with to_dict() method.
    """
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)


__all__ = [
    "OutputFormat",
    "console",
    "set_verbose",
    "is_verbose",
    "is_interactive",
    "output",
    "output_error",
    "print_table",
    "print_csv",
]
