---
id: mc-e3e1
status: closed
deps: [mc-7fb9, mc-3eba]
links: []
created: 2026-01-18T16:00:58Z
type: task
priority: 0
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, core, errors]
---
# Error Handler Decorator

Create decorator for consistent error handling across all CLI commands.

## Location
`src/monarch_cli/core/error_handler.py`

## Implementation
```python
import functools
import sys
import typer
from typing import Callable, TypeVar, ParamSpec

from .exceptions import MonarchCLIError
from ..output import output_error, is_verbose

P = ParamSpec("P")
R = TypeVar("R")

def handle_errors(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that catches exceptions and outputs consistent errors.
    
    Uses typer.Exit() instead of sys.exit() for better testability.
    """
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise typer.Exit(130)
        except MonarchCLIError as e:
            output_error(e)
            raise typer.Exit(e.exit_code)
        except Exception as e:
            if is_verbose():
                import traceback
                traceback.print_exc()
            output_error(MonarchCLIError(f"Unexpected error: {e}"))
            raise typer.Exit(1)
    return wrapper
```

## Usage Pattern
```python
@app.command()
@handle_errors  # Apply to all commands
def list_accounts(format: OutputFormat = ...):
    accounts = account_service.list_accounts()
    output(accounts, format)
```

## Design Decisions
1. **typer.Exit() vs sys.exit()**: typer.Exit() works better with CliRunner in tests
2. **Verbose mode**: Shows full traceback for debugging when --verbose is set
3. **Output to stderr**: Errors go to stderr to preserve stdout for data piping
4. **functools.wraps**: Preserves function metadata for Typer's help generation

## Note on Signal Handling
Typer handles SIGINT (Ctrl-C) automatically with proper cleanup. The decorator catches KeyboardInterrupt for cases where async code might raise it.

## Acceptance Criteria

- [ ] @handle_errors decorator implemented
- [ ] Catches and formats MonarchCLIError exceptions
- [ ] Catches and wraps unexpected exceptions
- [ ] Handles KeyboardInterrupt with exit code 130
- [ ] Shows traceback in verbose mode
- [ ] Uses typer.Exit() for testability
- [ ] Unit tests for each exception type

