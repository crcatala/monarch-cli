"""Unit tests for the live-suite subprocess throttle.

These are ordinary, non-live tests: they never spawn a CLI subprocess or call
the Monarch API, so they run in the default ``-m "not live"`` suite and give CI
coverage for the throttling behavior that would otherwise only be observable in
a credential-gated live run.
"""

from __future__ import annotations

import pytest

from tests.live import test_live_api as live


class _FakeClock:
    """Deterministic stand-in for ``time.monotonic``/``time.sleep``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(live, "_last_call_at", None)
    monkeypatch.setattr(live.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(live.time, "sleep", clock.sleep)
    return clock


def test_first_call_does_not_sleep(fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "LIVE_DELAY", 1.0)

    live._wait_for_api_throttle()

    assert fake_clock.sleeps == []
    assert live._last_call_at == fake_clock.now


def test_consecutive_call_waits_remaining_delay(
    fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "LIVE_DELAY", 1.0)

    live._wait_for_api_throttle()
    fake_clock.now += 0.25
    live._wait_for_api_throttle()

    assert fake_clock.sleeps == pytest.approx([0.75])


def test_no_wait_after_delay_elapsed(
    fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "LIVE_DELAY", 1.0)

    live._wait_for_api_throttle()
    fake_clock.now += 5.0
    live._wait_for_api_throttle()

    assert fake_clock.sleeps == []


def test_zero_delay_disables_throttling(
    fake_clock: _FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "LIVE_DELAY", 0.0)

    live._wait_for_api_throttle()
    fake_clock.now += 0.1
    live._wait_for_api_throttle()

    assert fake_clock.sleeps == []
