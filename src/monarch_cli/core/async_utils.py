"""Async utilities for bridging async library calls to sync CLI commands.

The monarchmoneycommunity library is fully async, while Typer commands are sync.
This module provides clean bridging utilities.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable, Coroutine

from .config import get_config
from .exceptions import ErrorCode, MonarchCLIError, MutationAmbiguousError, NetworkError
from .retry import RETRYABLE_EXCEPTIONS, MutationRetryPolicy


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


# --- Mutation execution (retry-safe, ambiguity-aware) ----------------------

#: Exceptions that leave the outcome of an already-dispatched request unknown.
#: For a remote mutation, any of these after the request has been invoked
#: means the service may have received and processed it: the result is
#: ambiguous, not merely failed.
AMBIGUOUS_TRANSPORT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    *RETRYABLE_EXCEPTIONS,
    asyncio.CancelledError,
)


def _classify_ambiguity(exc: BaseException) -> str:
    """Map an ambiguous transport failure to a stable reason label.

    Labels are coarse and stable by design; raw exception text is never
    included in mutation ambiguity output.
    """
    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
        # Includes Ctrl-C (KeyboardInterrupt is delivered to the main thread,
        # outside the coroutine, and cancels the running task).
        return "cancelled"
    if isinstance(exc, TimeoutError):
        # Includes asyncio.timeout expiry and aiohttp server timeouts.
        return "timeout"
    return "transport_failure"


def _default_verification(entity_ids: tuple[str, ...]) -> str:
    if entity_ids:
        return (
            "Verify the affected record(s) "
            f"({', '.join(entity_ids)}) via read commands or the Monarch web "
            "UI to confirm whether the change was applied before retrying."
        )
    return (
        "Verify the affected record(s) via read commands or the Monarch web UI "
        "to confirm whether the change was applied before retrying."
    )


def _mutation_ambiguous_error(
    *,
    operation: str,
    entity_ids: tuple[str, ...],
    verification: str | None,
    cause: BaseException,
    timeout_seconds: float,
) -> MutationAmbiguousError:
    """Build the structured ambiguity error for an uncertain mutation."""
    reason = _classify_ambiguity(cause)
    verification_text = verification or _default_verification(entity_ids)
    return MutationAmbiguousError(
        message=(
            f"Mutation '{operation}' could not be confirmed ({reason} after the "
            "request may have been dispatched). Remote state may have changed; "
            "do not retry blindly. Verify first: "
            f"{verification_text}"
        ),
        details={
            "operation": operation,
            "entity_ids": list(entity_ids),
            "remote_state": "unknown",
            "reason": reason,
            "timeout_seconds": timeout_seconds,
            "attempts": 1,
            "verification": verification_text,
        },
    )


def _validate_mutation_retry_policy(retry_policy: MutationRetryPolicy) -> None:
    """Refuse any mutation retry policy that has not been earned.

    Only NO_RETRY is implemented. Selecting a named mechanism before its
    operation-specific tests exist is a policy violation, not a runtime
    decision; there is deliberately no generic boolean override.
    """
    if retry_policy is MutationRetryPolicy.NO_RETRY:
        return
    raise MonarchCLIError(
        message=(
            f"Retry policy '{retry_policy.value}' is not implemented for "
            "mutations: enabling automatic retry requires a named, "
            "operation-specific idempotency mechanism (upstream idempotency "
            "key or tested read-after-write verification) with "
            "operation-specific tests. There is no generic retry override."
        ),
        code=ErrorCode.POLICY_VIOLATION,
        exit_code=1,
    )


async def run_mutation_api_call_async[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    operation: str,
    entity_ids: tuple[str, ...] | list[str] = (),
    verification: str | None = None,
    timeout_seconds: float | None = None,
    retry_policy: MutationRetryPolicy = MutationRetryPolicy.NO_RETRY,
) -> T:
    """Execute a remote mutation exactly once, with a per-attempt timeout.

    This is the single-attempt execution path for remote mutations. It is
    deliberately separate from :func:`run_api_call` (the read path):

    - **No automatic retries, regardless of configuration.** A timed-out,
      disconnected, or cancelled mutation may already have been applied by
      the service; a second attempt can duplicate the side effect. Reads keep
      their configured bounded retries; mutations never inherit them.
    - **Ambiguity is distinct from failure.** If the request may have been
      dispatched and the outcome is unknown, this raises
      :class:`MutationAmbiguousError` (exit code 4) identifying the operation
      and affected entities with a safe verification step. A definite
      application-level rejection propagates unchanged on the normal API
      error path.

    Args:
        coro_factory: Callable that creates the mutation coroutine.
        operation: Stable operation name (e.g. ``transactions update``).
        entity_ids: Identifiers of the records the mutation targets.
        verification: Domain-appropriate safe verification instruction;
            a generic instruction is generated when omitted.
        timeout_seconds: Per-attempt timeout override (default: from config).
        retry_policy: Mutation retry policy; only ``NO_RETRY`` is supported.

    Returns:
        The result of the mutation call.

    Raises:
        MutationAmbiguousError: On timeout, disconnect, cancellation after
            invocation, or another ambiguous transport failure.
        MonarchCLIError: POLICY_VIOLATION if a non-``NO_RETRY`` policy is
            selected.
    """
    _validate_mutation_retry_policy(retry_policy)
    config = get_config()
    effective_timeout = timeout_seconds if timeout_seconds is not None else config.timeout_seconds
    ids = tuple(entity_ids)

    try:
        async with asyncio.timeout(effective_timeout):
            return await coro_factory()
    except AMBIGUOUS_TRANSPORT_EXCEPTIONS as e:
        raise _mutation_ambiguous_error(
            operation=operation,
            entity_ids=ids,
            verification=verification,
            cause=e,
            timeout_seconds=effective_timeout,
        ) from e


def run_mutation_api_call[T](
    coro_factory: Callable[[], Awaitable[T]],
    *,
    operation: str,
    entity_ids: tuple[str, ...] | list[str] = (),
    verification: str | None = None,
    timeout_seconds: float | None = None,
    retry_policy: MutationRetryPolicy = MutationRetryPolicy.NO_RETRY,
) -> T:
    """Synchronous bridge for the single-attempt mutation executor.

    See :func:`run_mutation_api_call_async` for the retry-safety and
    ambiguity semantics. The timeout applies per attempt; there is exactly
    one attempt.

    A ``KeyboardInterrupt`` (Ctrl-C) delivered while the mutation runs is
    converted into ``MutationAmbiguousError``: the interrupt stops the event
    loop before the coroutine's own ambiguity conversion can surface, and a
    request that was already dispatched must never be reported as a plain
    "Interrupted." exit 130 with no verification guidance.
    """
    config = get_config()
    effective_timeout = timeout_seconds if timeout_seconds is not None else config.timeout_seconds
    mutation_coro = run_mutation_api_call_async(
        coro_factory,
        operation=operation,
        entity_ids=entity_ids,
        verification=verification,
        timeout_seconds=timeout_seconds,
        retry_policy=retry_policy,
    )
    try:
        return run_async(mutation_coro)
    except BaseException as e:
        # If the bridge is interrupted before it can hand the coroutine to an
        # event loop (as in a synchronous caller/test), close it explicitly so
        # Python does not emit an unawaited-coroutine warning. ``close`` is
        # harmless when asyncio.run already cancelled and closed the coroutine.
        mutation_coro.close()
        if not isinstance(e, KeyboardInterrupt):
            raise
        # The interrupt cancelled the running task; the coroutine's internal
        # ambiguity conversion cannot surface through asyncio.run() shutdown,
        # so report it here. This is conservative: even if the interrupt
        # landed before dispatch, claiming ambiguity never understates risk.
        raise _mutation_ambiguous_error(
            operation=operation,
            entity_ids=tuple(entity_ids),
            verification=verification,
            cause=e,
            timeout_seconds=effective_timeout,
        ) from e
