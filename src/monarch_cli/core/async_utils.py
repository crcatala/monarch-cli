"""Async utilities for bridging async library calls to sync CLI commands.

The monarchmoneycommunity library is fully async, while Typer commands are sync.
This module provides clean bridging utilities.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine


def run_async[T](coro: Coroutine[object, object, T]) -> T:
    """Execute an async coroutine synchronously.

    Bridges the async monarchmoneycommunity library with sync Typer commands.

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.

    Raises:
        KeyboardInterrupt: Propagated if user interrupts execution.
        RuntimeError: If the coroutine was cancelled.

    Example:
        >>> from monarch_cli.core.async_utils import run_async
        >>> accounts = run_async(client.get_accounts())
    """
    try:
        return asyncio.run(coro)
    except asyncio.CancelledError as e:
        raise RuntimeError("Operation was cancelled") from e
    except KeyboardInterrupt:
        # Propagate keyboard interrupt without wrapping
        raise
