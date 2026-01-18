---
id: mc-3eba
status: closed
deps: [mc-7fb9]
links: []
created: 2026-01-18T16:02:26Z
type: task
priority: 0
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, output, bootstrap]
---
# Minimal Output Helpers (Bootstrap)

Create minimal output helpers for Phase 1 auth commands. Full output system comes in Phase 2.

## Location
`src/monarch_cli/output/__init__.py`

## Scope (Bootstrap Version)
For Phase 1, we only need basic output for auth commands:
- Human-readable output via Rich console (default)
- JSON output via `--json` flag
- Error output to stderr
- Verbose flag tracking

## Design Philosophy

**Human-readable by default, JSON opt-in.** Auth commands output styled text by default, with `--json` flag for scripts/AI agents:

```bash
# Default: Human-readable
monarch auth status
# ✓ Authenticated
#   Backend: file

# Opt-in: JSON
monarch auth status --json
# {"authenticated": true, "storage_backend": "file", ...}
```

## Implementation
```python
import json
import sys
from enum import Enum
from typing import Any
from rich.console import Console

from ..core.exceptions import MonarchCLIError

class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    CSV = "csv"
    COMPACT = "compact"

# Rich console for styled output (uses stderr to keep stdout clean)
console = Console(stderr=True)

_verbose = False

def set_verbose(v: bool) -> None:
    global _verbose
    _verbose = v

def is_verbose() -> bool:
    return _verbose

def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
    """Output data as JSON to stdout. Used when --json flag is passed."""
    if format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))

def output_error(error: MonarchCLIError) -> None:
    """Output structured error for AI agents to stderr."""
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)
```

## Command Pattern
Auth commands use Rich console for human output, `output()` for JSON:

```python
@app.command()
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    if json_output:
        output({"authenticated": True, ...}, OutputFormat.JSON)
    else:
        console.print("[green]✓ Authenticated[/green]")
        console.print(f"  Backend: {backend}")
```

## Why Bootstrap First?
- Auth commands need output immediately
- Full output system (table, CSV, NDJSON) requires more work
- Phase 2 will expand this with full formatter support

## Rich Console
The Rich console uses stderr to keep stdout clean for data piping. Human-readable output goes to stderr, JSON data goes to stdout.

## Note on OutputFormat
The enum includes all formats for forward compatibility, but only JSON and COMPACT work in Phase 1. Phase 2 implements TABLE and CSV.

## Acceptance Criteria

- [x] OutputFormat enum with all values
- [x] output() function for JSON output (when --json passed)
- [x] output_error() outputs to stderr
- [x] Verbose flag getter/setter
- [x] Rich console available for interactive output
- [x] Human-readable output as default for auth commands
- [x] JSON output via --json flag
