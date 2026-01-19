"""Tests for monarch_cli.core.async_utils module."""

from __future__ import annotations

import asyncio

import pytest

from monarch_cli.core.async_utils import run_api_call, run_async
from monarch_cli.core.config import reset_config
from monarch_cli.core.exceptions import NetworkError


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


@pytest.fixture(autouse=True)
def clean_config(tmp_path, monkeypatch):
    """Reset config for each test."""
    monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
    reset_config()
    yield
    reset_config()


class TestRunApiCall:
    """Tests for run_api_call function with timeout and retry."""

    def test_executes_successfully(self) -> None:
        """Should execute coroutine factory and return result."""
        call_count = 0

        async def api_call() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = run_api_call(lambda: api_call())
        assert result == "success"
        assert call_count == 1

    def test_retries_on_connection_error(self) -> None:
        """Should retry on ConnectionError and eventually succeed."""
        call_count = 0

        async def flaky_api() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"

        result = run_api_call(lambda: flaky_api(), max_retries=3)
        assert result == "success"
        assert call_count == 3

    def test_raises_network_error_after_retries_exhausted(self) -> None:
        """Should raise NetworkError after all retries fail."""
        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent failure")

        with pytest.raises(NetworkError) as exc_info:
            run_api_call(lambda: always_fails(), max_retries=2)

        assert "3 attempts" in str(exc_info.value)
        assert call_count == 3  # Initial + 2 retries

    def test_timeout_triggers_network_error(self) -> None:
        """Should raise NetworkError when timeout is exceeded."""

        async def slow_api() -> str:
            await asyncio.sleep(10)  # Very slow
            return "never reached"

        with pytest.raises(NetworkError) as exc_info:
            run_api_call(lambda: slow_api(), timeout_seconds=0.1, max_retries=0)

        assert "timed out" in str(exc_info.value).lower()

    def test_timeout_retries(self) -> None:
        """Should retry on timeout and eventually succeed."""
        call_count = 0

        async def slow_then_fast() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                await asyncio.sleep(10)  # Timeout on first call
            return "success"

        result = run_api_call(lambda: slow_then_fast(), timeout_seconds=0.1, max_retries=2)
        assert result == "success"
        assert call_count == 2

    def test_uses_config_defaults(self, tmp_path) -> None:
        """Should use timeout and max_retries from config."""
        # Create config file with custom values
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
timeout = 5
max_retries = 1
""")
        reset_config()

        call_count = 0

        async def flaky_api() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("First failure")
            return "success"

        # Should use max_retries=1 from config
        result = run_api_call(lambda: flaky_api())
        assert result == "success"
        assert call_count == 2  # Initial + 1 retry

    def test_override_config_values(self, tmp_path) -> None:
        """Should allow overriding config values."""
        # Create config file with values
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
timeout = 30
max_retries = 5
""")
        reset_config()

        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Failure")

        # Override max_retries to 1
        with pytest.raises(NetworkError):
            run_api_call(lambda: always_fails(), max_retries=1)

        assert call_count == 2  # Initial + 1 retry (not 5 from config)

    def test_non_retryable_error_propagates(self) -> None:
        """Should not retry non-network errors."""
        call_count = 0

        async def value_error_api() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Bad input")

        with pytest.raises(ValueError, match="Bad input"):
            run_api_call(lambda: value_error_api(), max_retries=3)

        assert call_count == 1  # No retries for ValueError

    def test_os_error_is_retried(self) -> None:
        """Should retry on OSError (network-related)."""
        call_count = 0

        async def os_error_api() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("Network unreachable")
            return "success"

        result = run_api_call(lambda: os_error_api(), max_retries=2)
        assert result == "success"
        assert call_count == 2

    def test_preserves_return_type(self) -> None:
        """Should preserve the return type from the coroutine."""

        async def returns_dict() -> dict:
            return {"key": "value", "count": 42}

        result = run_api_call(lambda: returns_dict())
        assert result == {"key": "value", "count": 42}
        assert isinstance(result, dict)
