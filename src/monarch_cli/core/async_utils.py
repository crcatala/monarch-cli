"""Async utilities for bridging async library calls to sync CLI commands.

The monarchmoneycommunity library is fully async, while Typer commands are sync.
This module provides clean bridging utilities.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable, Coroutine

from .config import get_config
from .exceptions import NetworkError
from .retry import RETRYABLE_EXCEPTIONS


def _run_in_new_loop[T](coro: Coroutine[object, object, T]) -> T:
    """Run coroutine in a new event loop in the current thread.

    Helper for run_async when called from a thread without a running loop.
    """
    return asyncio.run(coro)


def run_async[T](coro: Coroutine[object, object, T]) -> T:
    """Execute an async coroutine synchronously.

    Bridges the async monarchmoneycommunity library with sync Typer commands.
    Handles both cases:
    - Normal CLI usage: Uses asyncio.run() directly
    - Nested event loop (Jupyter, async context): Runs in a separate thread

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.

    Raises:
        KeyboardInterrupt: Propagated if user interrupts execution.
        RuntimeError: If the coroutine was cancelled or thread execution failed.

    Example:
        >>> from monarch_cli.core.async_utils import run_async
        >>> accounts = run_async(client.get_accounts())
    """
    try:
        # Check if there's already a running event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in an async context (Jupyter, nested async, etc.)
            # Run in a separate thread with its own event loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_in_new_loop, coro)
                try:
                    return future.result()
                except concurrent.futures.CancelledError as e:
                    raise RuntimeError("Operation was cancelled") from e
        else:
            # Normal case: no running loop, use asyncio.run directly
            return asyncio.run(coro)

    except asyncio.CancelledError as e:
        raise RuntimeError("Operation was cancelled") from e
    except KeyboardInterrupt:
        # Propagate keyboard interrupt without wrapping
        raise


def run_async_iter[T](
    coro: Coroutine[object, object, T],
) -> T:
    """Execute an async coroutine, optimized for iteration contexts.

    Alias for run_async. Provided for semantic clarity when used in loops.

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.
    """
    return run_async(coro)


async def _with_timeout_and_retry[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    timeout_seconds: float,
    max_retries: int,
) -> T:
    """Execute an async operation with timeout and retry.

    Combines timeout and retry logic. The timeout applies to each individual
    attempt, not the total time across all retries.

    Args:
        coro_factory: Callable that creates a new coroutine each attempt.
        timeout_seconds: Timeout for each attempt in seconds.
        max_retries: Maximum number of retry attempts.

    Returns:
        The result of the successful coroutine execution.

    Raises:
        NetworkError: After exhausting all retry attempts or on timeout.
    """
    last_exception: BaseException | None = None

    for attempt in range(max_retries + 1):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await coro_factory()
        except TimeoutError as e:
            last_exception = e
            if attempt == max_retries:
                break
            # TimeoutError is retryable, continue to next attempt
            await asyncio.sleep(min(1.0 * (2**attempt), 30.0))
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e
            if attempt == max_retries:
                break
            await asyncio.sleep(min(1.0 * (2**attempt), 30.0))

    # All retries exhausted
    if isinstance(last_exception, TimeoutError):
        raise NetworkError(
            message=f"Request timed out after {timeout_seconds}s ({max_retries + 1} attempts)",
            details={
                "timeout_seconds": timeout_seconds,
                "attempts": max_retries + 1,
            },
        )
    raise NetworkError(
        message=f"Operation failed after {max_retries + 1} attempts: {last_exception}",
        details={"attempts": max_retries + 1, "last_error": str(last_exception)},
    )


def run_api_call[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> T:
    """Execute an API call with timeout and retry from config.

    This is the recommended way to make API calls. It automatically applies
    timeout and retry settings from the global config, with optional overrides.

    Args:
        coro_factory: Callable that creates the API coroutine.
                      Must be a factory (lambda) because coroutines can only
                      be awaited once, and retries need fresh coroutines.
        timeout_seconds: Override timeout (default: from config).
        max_retries: Override max retries (default: from config).

    Returns:
        The result of the API call.

    Raises:
        NetworkError: On timeout or after exhausting retries.
        AuthenticationError: If not authenticated.
        APIError: If the API returns an error.

    Example:
        >>> from monarch_cli.core.async_utils import run_api_call
        >>> from monarch_cli.core.adapter import get_authenticated_client
        >>> client = get_authenticated_client()
        >>> accounts = run_api_call(lambda: client.get_accounts())
        >>> # With custom timeout for slow operation:
        >>> data = run_api_call(lambda: client.get_transactions(), timeout_seconds=60)
    """
    config = get_config()
    effective_timeout = timeout_seconds if timeout_seconds is not None else config.timeout_seconds
    effective_retries = max_retries if max_retries is not None else config.max_retries

    return run_async(
        _with_timeout_and_retry(
            coro_factory,
            timeout_seconds=effective_timeout,
            max_retries=effective_retries,
        )
    )
