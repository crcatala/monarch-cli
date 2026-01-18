---
id: mc-3eba
status: open
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
- JSON output (default)
- Error output to stderr
- Verbose flag tracking

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

console = Console()
_verbose = False

def set_verbose(v: bool) -> None:
    global _verbose
    _verbose = v

def is_verbose() -> bool:
    return _verbose

def output(data: Any, format: OutputFormat = OutputFormat.JSON) -> None:
    """Output data in specified format. Table/CSV support added in Phase 2."""
    if format == OutputFormat.COMPACT:
        print(json.dumps(data, default=str))
    else:
        print(json.dumps(data, indent=2, default=str))

def output_error(error: MonarchCLIError) -> None:
    """Output structured error for AI agents to stderr."""
    print(json.dumps(error.to_dict(), indent=2), file=sys.stderr)
```

## Why Bootstrap First?
- Auth commands need output immediately
- Full output system (table, CSV, NDJSON) requires more work
- Phase 2 will expand this with full formatter support

## Rich Console
The rich console is initialized for use by auth commands that display interactive content (login prompts, doctor output). The console uses stderr to keep stdout clean for data.

## Note on OutputFormat
The enum includes all formats for forward compatibility, but only JSON and COMPACT work in Phase 1. Phase 2 implements TABLE and CSV.

## Acceptance Criteria

- [ ] OutputFormat enum with all values
- [ ] output() function for basic JSON output
- [ ] output_error() outputs to stderr
- [ ] Verbose flag getter/setter
- [ ] Rich console available for interactive output
- [ ] COMPACT format outputs single-line JSON
- [ ] JSON format outputs indented JSON

