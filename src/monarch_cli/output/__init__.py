"""
Bootstrap output helpers for Phase 1 auth commands.

This provides minimal output functionality needed for authentication commands.
Full output system (table, CSV, NDJSON) will be implemented in Phase 2.
"""

import json
import sys
from enum import Enum
from typing import Any

from rich.console import Console

from ..core.exceptions import MonarchCLIError


class OutputFormat(str, Enum):
    """Output format options.

    Note: Only JSON and COMPACT are implemented in Phase 1.
    TABLE and CSV support will be added in Phase 2.
    """

    JSON = "json"
    TABLE = "table"
    CSV = "csv"
    COMPACT = "compact"


# Rich console for styled interactive output (uses stderr to keep stdout clean)
console = Console(stderr=True)

# Module-level verbose flag
_verbose = False


def set_verbose(v: bool) -> None:
    """Set the verbose output flag."""
    global _verbose
    _verbose = v


def is_verbose() -> bool:
    """Check if verbose output is enabled."""
    return _verbose


def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
    """Output data in specified format.

    Args:
        data: Data to output (will be JSON serialized).
        format: Output format (only JSON and COMPACT supported in Phase 1).

    Note:
        TABLE and CSV support will be added in Phase 2.
        For now, both fall back to JSON output.
    """
    if format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    else:
        # JSON, TABLE, CSV all output as indented JSON for now
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
    "output",
    "output_error",
]
