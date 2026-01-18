"""Tests for monarch_cli.core.async_utils module."""

from __future__ import annotations

import asyncio

import pytest

from monarch_cli.core.async_utils import run_async


class TestRunAsync:
    """Tests for run_async function."""

    def test_executes_coroutine(self) -> None:
        """Should execute coroutine and return result."""

        async def sample_coro() -> str:
            return "result"

        result = run_async(sample_coro())
        assert result == "result"

    def test_preserves_return_type(self) -> None:
        """Should preserve the return type of the coroutine."""

        async def returns_int() -> int:
            return 42

        async def returns_list() -> list[str]:
            return ["a", "b", "c"]

        assert run_async(returns_int()) == 42
        assert run_async(returns_list()) == ["a", "b", "c"]

    def test_propagates_exception(self) -> None:
        """Should propagate exceptions from coroutine."""

        async def raises_error() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            run_async(raises_error())

    def test_handles_nested_event_loop(self) -> None:
        """Should work when called from within an async context."""

        async def inner() -> str:
            return "inner result"

        async def outer() -> str:
            # This simulates calling run_async from an async context
            return run_async(inner())

        # Run the outer coroutine which calls run_async
        result = asyncio.run(outer())
        assert result == "inner result"

    def test_cancelled_error_becomes_runtime_error(self) -> None:
        """Should convert CancelledError to RuntimeError."""

        async def gets_cancelled() -> None:
            raise asyncio.CancelledError()

        with pytest.raises(RuntimeError, match="cancelled"):
            run_async(gets_cancelled())

    def test_keyboard_interrupt_propagates(self) -> None:
        """Should propagate KeyboardInterrupt without wrapping."""

        async def interrupted() -> None:
            raise KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            run_async(interrupted())

    def test_async_sleep_works(self) -> None:
        """Should properly handle async operations like sleep."""

        async def with_sleep() -> str:
            await asyncio.sleep(0.01)
            return "after sleep"

        result = run_async(with_sleep())
        assert result == "after sleep"

    def test_multiple_calls(self) -> None:
        """Should work correctly with multiple sequential calls."""
        counter = 0

        async def increment() -> int:
            nonlocal counter
            counter += 1
            return counter

        assert run_async(increment()) == 1
        assert run_async(increment()) == 2
        assert run_async(increment()) == 3
