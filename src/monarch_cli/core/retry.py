"""Retry logic with exponential backoff for network resilience.

Provides retry functionality for transient network errors with configurable
exponential backoff and jitter to prevent thundering herd.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from enum import StrEnum

import aiohttp
from gql.transport.exceptions import TransportConnectionFailed

from .exceptions import NetworkError


class MutationRetryPolicy(StrEnum):
    """Retry policy for remote mutations.

    The only policy implemented today is :attr:`NO_RETRY`: no current
    mutation is known to be idempotent, so a second automatic attempt could
    duplicate an undocumented side effect.

    A future retry-enabled mutation must select a *named*, operation-specific
    mechanism (an upstream idempotency key, or a tested read-after-write
    verification) rather than a generic boolean override. Those reserved
    values exist so the selection point is explicit; selecting one before its
    operation-specific mechanism and tests exist is refused by the mutation
    executor.
    """

    #: Never retry. The default and only supported policy for mutations.
    NO_RETRY = "no_retry"
    #: Reserved: requires an upstream idempotency key plus operation-specific
    #: tests proving duplicate suppression before it may be implemented.
    IDEMPOTENCY_KEY = "idempotency_key"
    #: Reserved: requires tested read-after-write verification plus
    #: operation-specific tests before it may be implemented.
    READ_AFTER_WRITE = "read_after_write"


# Exceptions that are safe to retry - typically transient network issues.
# Includes stdlib exceptions, aiohttp-specific exceptions, and the gql
# transport wrapper that every upstream API call passes through.
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
    # gql transport failures. The upstream monarchmoney client executes every
    # call through gql, whose aiohttp transport wraps all connection-level
    # failures (including the aiohttp types above) as
    # ``TransportConnectionFailed``. Without this entry a real transport
    # failure is neither retried on the read path nor classified as
    # ambiguous on the mutation path.
    TransportConnectionFailed,
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
