"""Retry logic with exponential backoff for network resilience.

Provides retry functionality for transient network errors with configurable
exponential backoff and jitter to prevent thundering herd.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

import aiohttp

from .exceptions import NetworkError

# Exceptions that are safe to retry - typically transient network issues.
# Includes both stdlib exceptions and aiohttp-specific exceptions since
# monarchmoney uses aiohttp for HTTP requests.
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    # Standard library exceptions
    ConnectionError,
    TimeoutError,
    OSError,
    # aiohttp exceptions (monarchmoney uses aiohttp)
    aiohttp.ClientConnectionError,
    aiohttp.ServerConnectionError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ServerTimeoutError,
)


async def with_retry[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> T:
    """Execute an async operation with exponential backoff retry.

    Uses a factory pattern because coroutines can only be awaited once.
    The factory creates a fresh coroutine for each retry attempt.

    Args:
        coro_factory: Callable that creates a new coroutine each attempt.
        max_retries: Maximum retry attempts (default 3).
        base_delay: Initial delay in seconds (default 1.0).
        max_delay: Maximum delay cap in seconds (default 30.0).
        jitter: Add randomness to prevent thundering herd (default True).

    Returns:
        The result of the successful coroutine execution.

    Raises:
        NetworkError: After exhausting all retry attempts.

    Example:
        >>> from monarch_cli.core.retry import with_retry
        >>> result = await with_retry(lambda: client.get_accounts())
        >>> # With custom settings:
        >>> result = await with_retry(
        ...     lambda: client.get_accounts(),
        ...     max_retries=5,
        ...     base_delay=0.5,
        ... )
    """
    last_exception: BaseException | None = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e
            if attempt == max_retries:
                # No more retries, break out and raise NetworkError
                break

            # Calculate exponential backoff delay
            delay = min(base_delay * (2**attempt), max_delay)

            # Add jitter (0.75 to 1.25 multiplier) to prevent thundering herd
            if jitter:
                jitter_multiplier = 0.75 + random.random() * 0.5
                delay = delay * jitter_multiplier

            await asyncio.sleep(delay)

    # All retries exhausted
    raise NetworkError(
        message=f"Operation failed after {max_retries + 1} attempts: {last_exception}",
        details={"attempts": max_retries + 1, "last_error": str(last_exception)},
    )
