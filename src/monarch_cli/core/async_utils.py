"""Async utilities for bridging async library calls to sync CLI commands.

The monarchmoneycommunity library is fully async, while Typer commands are sync.
This module provides clean bridging utilities.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine


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
