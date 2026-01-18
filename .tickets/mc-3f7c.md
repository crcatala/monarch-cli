---
id: mc-3f7c
status: closed
deps: [mc-299b]
links: []
created: 2026-01-18T16:03:59Z
type: task
priority: 1
assignee: cc-vps
parent: mc-0e26
tags: [phase-2, output, ux]
---
# Progress Indicators

Implement progress indicators (spinners) for long-running operations.

## Location
`src/monarch_cli/output/progress.py`

## Implementation
```python
import sys
from contextlib import contextmanager
from typing import Generator

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console(stderr=True)  # Progress to stderr

def is_interactive() -> bool:
    """Check if we're in an interactive terminal."""
    return sys.stderr.isatty()

@contextmanager
def spinner(message: str) -> Generator[None, None, None]:
    """Show a spinner while an operation is in progress.
    
    Only shows spinner in interactive terminals.
    """
    if not is_interactive():
        console.print(f"[dim]{message}[/dim]")
        yield
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,  # Remove spinner when done
    ) as progress:
        progress.add_task(description=message, total=None)
        yield
```

## Usage in Commands
```python
@app.command()
def list_accounts(...):
    with spinner("Fetching accounts..."):
        accounts = run_async(client.get_accounts())
    output(accounts, format)
```

## Why Progress to stderr?
- Keeps stdout clean for data output
- Allows piping: `monarch accounts list | jq ...` shows spinner while fetching
- Rich's transient=True removes spinner when done

## TTY Detection
- Interactive terminal: Show animated spinner with elapsed time
- Non-TTY (piped): Print simple message (no animation)

## Response Time Guideline
From clig.dev: Print something within 100ms. The spinner provides immediate feedback before network I/O, so users know the command is working.

## Console Configuration
- Use `Console(stderr=True)` to ensure progress goes to stderr
- `transient=True` removes the spinner line after completion
- TimeElapsedColumn shows how long the operation is taking

## Acceptance Criteria

- [ ] spinner() context manager implemented
- [ ] Spinner shows in interactive terminals
- [ ] Fallback message in non-TTY contexts
- [ ] Progress output goes to stderr
- [ ] Spinner is transient (removed when done)
- [ ] Elapsed time displayed
- [ ] Works correctly with async operations

