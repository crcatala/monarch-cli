---
id: mc-dcbf
status: open
deps: [mc-9441]
links: []
created: 2026-01-18T16:00:25Z
type: task
priority: 0
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, core, async]
---
# Async Utilities Module

Create async utilities for running async code from synchronous Typer commands.

## Location
`src/monarch_cli/core/async_utils.py`

## Implementation
The `monarchmoneycommunity` library is fully async, but Typer commands are synchronous. We need a utility to bridge this gap.

```python
import asyncio
from typing import TypeVar, Coroutine, Any

T = TypeVar("T")

def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run async coroutine in sync context.
    
    Uses asyncio.run() which is the standard approach for CLI applications.
    Properly handles cleanup and exception propagation.
    """
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        raise
    except asyncio.CancelledError:
        raise RuntimeError("Operation was cancelled")
```

## Why asyncio.run()?
- Standard approach for CLI applications (not long-running servers)
- Creates new event loop each call, properly cleans up
- Alternative approaches (get_event_loop, nest_asyncio) have edge cases

## Usage Pattern
```python
from monarch_cli.core.async_utils import run_async
from monarchmoney import MonarchMoney

client = MonarchMoney(token=token)
accounts = run_async(client.get_accounts())  # Sync call to async method
```

## Error Handling
- KeyboardInterrupt: Re-raise for proper Ctrl-C handling
- CancelledError: Convert to RuntimeError with message
- Other exceptions: Propagate unchanged

## Acceptance Criteria

- [ ] `run_async()` function implemented
- [ ] Properly handles KeyboardInterrupt
- [ ] Properly handles asyncio.CancelledError
- [ ] Type hints with TypeVar for generic return type
- [ ] Unit test verifying basic functionality

