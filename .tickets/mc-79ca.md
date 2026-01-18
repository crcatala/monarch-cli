---
id: mc-79ca
status: open
deps: [mc-7fb9]
links: []
created: 2026-01-18T16:01:54Z
type: task
priority: 1
assignee: cc-vps
parent: mc-a23d
tags: [phase-1, core, reliability]
---
# Retry Logic with Exponential Backoff

Implement retry logic with exponential backoff for network resilience.

## Location
`src/monarch_cli/core/retry.py`

## Implementation
```python
import asyncio
import random
from typing import TypeVar, Callable, Awaitable

T = TypeVar("T")

RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> T:
    """Execute an async operation with exponential backoff retry.
    
    Args:
        coro_factory: Callable that creates a new coroutine each attempt
        max_retries: Maximum retry attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay cap (default 30.0)
        jitter: Add randomness to prevent thundering herd (default True)
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e
            if attempt == max_retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            if jitter:
                delay = delay * (0.75 + random.random() * 0.5)
            await asyncio.sleep(delay)
    
    raise NetworkError(f"Operation failed after {max_retries} retries: {last_exception}")
```

## Usage
```python
result = await with_retry(lambda: client.get_accounts())
# Or with sync wrapper:
result = run_async(with_retry(lambda: client.get_accounts()))
```

## Why coro_factory Instead of Coroutine?
A coroutine can only be awaited once. By passing a factory function, we create a fresh coroutine for each retry attempt.

## Exponential Backoff Schedule (with jitter)
| Attempt | Base Delay | With Jitter (approx) |
|---------|------------|----------------------|
| 1 | 1s | 0.75-1.25s |
| 2 | 2s | 1.5-2.5s |
| 3 | 4s | 3-5s |
| 4 | 8s | 6-10s |

## Note on Rate Limiting
Monarch Money doesn't explicitly document rate limits. This retry logic handles transient network errors. If we discover rate limiting behavior, we can add RateLimitError detection here.

## MVP Scope
For MVP, retry is optional enhancement. The error handler catches network errors and provides clear messages. This module adds reliability for flaky connections.

## Acceptance Criteria

- [ ] with_retry() async function implemented
- [ ] Exponential backoff with configurable parameters
- [ ] Jitter option to prevent thundering herd
- [ ] Raises NetworkError after exhausting retries
- [ ] Only retries on network-related exceptions
- [ ] coro_factory pattern for retryable coroutines
- [ ] Unit tests with mock delays

