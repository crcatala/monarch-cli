"""Tests for monarch_cli.core.retry module."""

from __future__ import annotations

import asyncio
from unittest import mock

import aiohttp
import pytest

from monarch_cli.core.exceptions import NetworkError
from monarch_cli.core.retry import RETRYABLE_EXCEPTIONS, with_retry


class TestRetryableExceptions:
    """Tests for RETRYABLE_EXCEPTIONS tuple."""

    def test_includes_stdlib_exceptions(self) -> None:
        """Should include standard library network exceptions."""
        assert ConnectionError in RETRYABLE_EXCEPTIONS
        assert TimeoutError in RETRYABLE_EXCEPTIONS
        assert OSError in RETRYABLE_EXCEPTIONS

    def test_includes_aiohttp_exceptions(self) -> None:
        """Should include aiohttp-specific exceptions."""
        assert aiohttp.ClientConnectionError in RETRYABLE_EXCEPTIONS
        assert aiohttp.ServerConnectionError in RETRYABLE_EXCEPTIONS
        assert aiohttp.ServerDisconnectedError in RETRYABLE_EXCEPTIONS
        assert aiohttp.ServerTimeoutError in RETRYABLE_EXCEPTIONS


class TestWithRetry:
    """Tests for with_retry function."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """Should return result on first successful attempt."""
        call_count = 0

        async def succeeds() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await with_retry(succeeds)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self) -> None:
        """Should retry on ConnectionError."""
        call_count = 0

        async def fails_then_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection failed")
            return "success"

        result = await with_retry(fails_then_succeeds, base_delay=0.01)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_timeout_error(self) -> None:
        """Should retry on TimeoutError."""
        call_count = 0

        async def fails_then_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Timed out")
            return "success"

        result = await with_retry(fails_then_succeeds, base_delay=0.01)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_aiohttp_client_connection_error(self) -> None:
        """Should retry on aiohttp.ClientConnectionError."""
        call_count = 0

        async def fails_then_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise aiohttp.ClientConnectionError("Connection failed")
            return "success"

        result = await with_retry(fails_then_succeeds, base_delay=0.01)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_aiohttp_server_disconnected(self) -> None:
        """Should retry on aiohttp.ServerDisconnectedError."""
        call_count = 0

        async def fails_then_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise aiohttp.ServerDisconnectedError("Server disconnected")
            return "success"

        result = await with_retry(fails_then_succeeds, base_delay=0.01)
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_raises_network_error_after_max_retries(self) -> None:
        """Should raise NetworkError after exhausting retries."""

        async def always_fails() -> str:
            raise ConnectionError("Always fails")

        with pytest.raises(NetworkError) as exc_info:
            await with_retry(always_fails, max_retries=2, base_delay=0.01)

        assert "3 attempts" in exc_info.value.message
        assert exc_info.value.details["attempts"] == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_exceptions(self) -> None:
        """Should not retry on non-retryable exceptions."""
        call_count = 0

        async def raises_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError, match="Not retryable"):
            await with_retry(raises_value_error, max_retries=3, base_delay=0.01)

        assert call_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_max_retries_parameter(self) -> None:
        """Should respect max_retries parameter."""
        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Fail")

        with pytest.raises(NetworkError):
            await with_retry(always_fails, max_retries=5, base_delay=0.01)

        assert call_count == 6  # Initial + 5 retries

    @pytest.mark.asyncio
    async def test_exponential_backoff(self) -> None:
        """Should use exponential backoff for delays."""
        delays: list[float] = []
        call_count = 0

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)

        async def fails_three_times() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise ConnectionError("Fail")
            return "success"

        with mock.patch("monarch_cli.core.retry.asyncio.sleep", mock_sleep):
            await with_retry(fails_three_times, base_delay=1.0, max_delay=30.0, jitter=False)

        # Expected delays: 1.0, 2.0, 4.0 (exponential)
        assert len(delays) == 3
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0

    @pytest.mark.asyncio
    async def test_max_delay_cap(self) -> None:
        """Should cap delay at max_delay."""
        delays: list[float] = []
        call_count = 0

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)

        async def fails_many_times() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 5:
                raise ConnectionError("Fail")
            return "success"

        with mock.patch("monarch_cli.core.retry.asyncio.sleep", mock_sleep):
            await with_retry(
                fails_many_times, max_retries=5, base_delay=1.0, max_delay=5.0, jitter=False
            )

        # Delays should be capped at 5.0
        assert all(d <= 5.0 for d in delays)
        # With base_delay=1.0 and no jitter: 1, 2, 4, 5, 5 (capped)
        assert delays == [1.0, 2.0, 4.0, 5.0, 5.0]

    @pytest.mark.asyncio
    async def test_jitter_adds_randomness(self) -> None:
        """Should add jitter when enabled."""
        delays: list[float] = []
        call_count = 0

        async def mock_sleep(delay: float) -> None:
            delays.append(delay)

        async def fails_once() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Fail")
            return "success"

        # Run multiple times to verify jitter adds randomness
        all_delays: list[float] = []
        for _ in range(10):
            delays.clear()
            call_count = 0
            with mock.patch("monarch_cli.core.retry.asyncio.sleep", mock_sleep):
                await with_retry(fails_once, base_delay=1.0, jitter=True)
            all_delays.append(delays[0])

        # With jitter, delays should be in range [0.75, 1.25]
        assert all(0.75 <= d <= 1.25 for d in all_delays)
        # And there should be some variation (not all the same)
        assert len(set(all_delays)) > 1

    @pytest.mark.asyncio
    async def test_factory_pattern_calls_factory_each_attempt(self) -> None:
        """Should call factory for each attempt to create fresh coroutine."""
        factory_call_count = 0
        coro_call_count = 0

        def coro_factory() -> asyncio.coroutines:
            nonlocal factory_call_count

            async def tracked_coro() -> str:
                nonlocal coro_call_count
                coro_call_count += 1
                if coro_call_count < 3:
                    raise ConnectionError("Fail")
                return "success"

            factory_call_count += 1
            return tracked_coro()

        await with_retry(coro_factory, base_delay=0.01)

        # Factory should be called for each attempt (including retries)
        assert factory_call_count == 3
        # And each coroutine should have been executed
        assert coro_call_count == 3
