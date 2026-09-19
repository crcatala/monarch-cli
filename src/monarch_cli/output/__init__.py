"""
Full output system for monarch-cli.

Supports multiple output formats:
- PLAIN (human-friendly with emoji icons, TTY default)
- JSON (pretty, indented, piped default)
- COMPACT (single-line JSON)
- TABLE (Rich table for human reading)
- CSV (spreadsheet export)
"""

from __future__ import annotations

import csv
import json
import sys
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.table import Table

from ..core.exceptions import MonarchCLIError, ValidationError
from ..core.mutation_outcomes import outcome_exit_code
from .plain import format_plain, set_color_enabled, should_use_color

if TYPE_CHECKING:
    from ..core.config import Config


class OutputFormat(StrEnum):
    """Output format options."""

    PLAIN = "plain"
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

# Module-level debug flag (implies verbose)
_debug = False

# Module-level quiet flag (for ID-only output)
_quiet = False

# Module-level default format override (set by --json global flag or config)
_default_format_override: OutputFormat | None = None


def apply_config(config: Config) -> None:
    """Apply configuration to the output system.

    This wires up the Config values to the output module's state.

    Args:
        config: Config instance with resolved settings.
    """
    set_verbose(config.verbose)
    set_debug(config.debug)
    set_quiet(config.quiet)

    # Only override color when explicitly disabled.
    # When color=True (default), leave as None for auto-detection
    # (respects NO_COLOR, TERM=dumb, TTY detection).
    if not config.color:
        set_color_enabled(False)
    else:
        set_color_enabled(None)  # Auto-detect

    # Set default format from config (plain -> use TTY detection, others -> override)
    if config.format != "plain":
        set_default_format(OutputFormat(config.format))
    else:
        # For "plain", use TTY-aware detection (plain for TTY, json for piped)
        set_default_format(None)


def set_verbose(v: bool) -> None:
    """Set the verbose output flag."""
    global _verbose
    _verbose = v


def is_verbose() -> bool:
    """Check if verbose output is enabled."""
    return _verbose or _debug  # Debug implies verbose


def set_debug(d: bool) -> None:
    """Set the debug output flag.

    Debug mode shows stack traces on errors and implies verbose.
    """
    global _debug
    _debug = d


def is_debug() -> bool:
    """Check if debug output is enabled."""
    return _debug


def set_quiet(q: bool) -> None:
    """Set the quiet output flag.

    Quiet mode outputs only IDs, one per line. Designed for AI agent consumption.
    """
    global _quiet
    _quiet = q


def is_quiet() -> bool:
    """Check if quiet output is enabled."""
    return _quiet


def is_interactive() -> bool:
    """Check if stdout is a TTY (interactive terminal).

    Returns:
        True if stdout is connected to a terminal, False if piped/redirected.
    """
    return sys.stdout.isatty()


def set_default_format(fmt: OutputFormat | None) -> None:
    """Set the default output format override.

    Used by global --json flag to force JSON output.

    Args:
        fmt: Format to use as default, or None to use TTY-aware detection.
    """
    global _default_format_override
    _default_format_override = fmt


def get_default_format() -> OutputFormat:
    """Get the default output format.

    Returns PLAIN when stdout is a TTY (interactive terminal),
    JSON when piped or redirected.

    Returns:
        OutputFormat.PLAIN for TTY, OutputFormat.JSON otherwise.
    """
    # Check for explicit override first
    if _default_format_override is not None:
        return _default_format_override

    # TTY-aware default
    if sys.stdout.isatty():
        return OutputFormat.PLAIN
    else:
        return OutputFormat.JSON


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


def _project_display(data: Any, display_fields: tuple[str, ...] | None) -> Any:
    """Restrict records to the human display fields, preserving order.

    Only dict records are projected; non-dict entries pass through untouched.
    A ``None`` selection returns ``data`` unchanged.
    """
    if display_fields is None:
        return data

    def project(item: Any) -> Any:
        if isinstance(item, dict):
            return {field: item.get(field) for field in display_fields}
        return item

    if isinstance(data, list):
        return [project(item) for item in data]
    return project(data)


def output(
    data: Any,
    format: OutputFormat | None = None,
    raw: bool = False,
    quiet: bool | None = None,
    id_field: str = "id",
    display_fields: tuple[str, ...] | None = None,
) -> None:
    """Output data in specified format.

    Args:
        data: Data to output.
        format: Output format. If None, uses TTY-aware default:
                PLAIN for terminal, JSON when piped.
        raw: If True, print data as-is (pass-through).
        quiet: If True, output only IDs (one per line). If None, uses module flag.
        id_field: Field name to extract when in quiet mode (default: "id").
        display_fields: Optional ordered field selection for the concise
            formats (plain, table, compact). Machine-readable formats (JSON,
            CSV, and NDJSON) always keep the complete normalized fields;
            --raw is untouched. When ``None``, no projection is applied.

    Note:
        TABLE and CSV only work with list[dict] data.
        For non-list data, these formats fall back to JSON.
        Quiet mode takes precedence over format.
    """
    # Determine if quiet mode is active
    quiet_mode = quiet if quiet is not None else _quiet

    # Handle quiet mode - output only IDs
    if quiet_mode:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and id_field in item:
                    print(item[id_field])
                else:
                    print(item)
        elif isinstance(data, dict) and id_field in data:
            print(data[id_field])
        return

    # Raw pass-through
    if raw:
        print(data)
        return

    # Use TTY-aware default if format not specified
    if format is None:
        format = get_default_format()

    # Format-specific output
    if format == OutputFormat.PLAIN:
        # Plain text with emoji icons - use color detection
        print(format_plain(_project_display(data, display_fields)))

    elif format == OutputFormat.COMPACT:
        # Explicit contract decision: compact is a concise single-line summary
        # view, projected like the other human formats. NDJSON (--ndjson) is
        # the machine-readable streaming format and always carries the
        # complete normalized records, as do JSON and CSV.
        print(json.dumps(_project_display(data, display_fields), default=str))

    elif format == OutputFormat.TABLE:
        # TABLE only works for list of dicts
        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            print_table(_project_display(data, display_fields))
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


def validate_mutation_output() -> None:
    """Reject output selections incompatible with the mutation contract.

    Mutation outcomes and previews are always machine-readable JSON. ``--quiet``
    and an explicit format other than ``json`` would swallow or re-render the
    result, so they are rejected with a structured input error. This is called
    before any remote mutation is attempted (validation precedes authorization)
    as well as by :func:`emit_mutation_outcome`.

    Raises:
        ValidationError: If ``--quiet`` or a non-JSON explicit format is set.
    """
    if is_quiet():
        raise ValidationError(
            "Mutation outcomes are machine-readable JSON and cannot be combined with --quiet.",
            field="quiet",
            details={"remedy": "drop --quiet; mutation outcomes always emit JSON on stdout"},
        )
    if _default_format_override is not None and _default_format_override != OutputFormat.JSON:
        raise ValidationError(
            "Mutation outcomes always emit JSON and cannot use a non-JSON format.",
            field="format",
            details={
                "requested_format": _default_format_override.value,
                "remedy": "use --json or remove the explicit format selection",
            },
        )


def emit_mutation_outcome(outcome: dict[str, Any]) -> None:
    """Emit a mutation outcome or dry-run preview as JSON on stdout.

    Remote mutation outcomes and previews always emit JSON on stdout
    regardless of TTY state, so shell pipelines and agents always receive
    the ``mutation-outcome.v1`` envelope even on an interactive terminal.
    Progress and diagnostics stay on stderr.

    The contract forbids output selections that would swallow or re-render
    the result: ``--quiet`` and an explicit format other than ``json`` are
    rejected with a structured input error (``INVALID_INPUT``, exit 2).
    ``--json`` / ``-f json`` are accepted as already satisfied.

    Args:
        outcome: The mutation-outcome envelope (or preview) dict to emit.

    Raises:
        ValidationError: If ``--quiet`` or a non-JSON explicit format is set.
        typer.Exit: With the status-derived exit code when it is non-zero.
    """
    validate_mutation_output()
    print(json.dumps(outcome, indent=2, default=str))
    code = outcome_exit_code(outcome["status"])
    if code:
        raise typer.Exit(code)


def output_error(error: MonarchCLIError) -> None:
    """Output structured error for AI agent consumption.

    Outputs error as JSON to stderr for consistent machine-readable output.

    Args:
        error: MonarchCLIError instance with to_dict() method.
    """
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)


__all__ = [
    "OutputFormat",
    "apply_config",
    "console",
    "set_verbose",
    "is_verbose",
    "set_debug",
    "is_debug",
    "set_quiet",
    "is_quiet",
    "is_interactive",
    "set_default_format",
    "get_default_format",
    "validate_mutation_output",
    "emit_mutation_outcome",
    "should_use_color",
    "output",
    "output_error",
    "print_table",
    "print_csv",
]
