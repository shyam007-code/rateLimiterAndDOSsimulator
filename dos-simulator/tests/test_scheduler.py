"""Unit tests for RateScheduler pacing."""

from __future__ import annotations

import asyncio

import pytest

from app.simulation.scheduler import RateScheduler
from tests.conftest import FakeClock


class ManualSleeper:
    """Records sleep calls and advances a FakeClock instead of really waiting."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


def test_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError):
        RateScheduler(target_rps=0, start_time=0.0)
    with pytest.raises(ValueError):
        RateScheduler(target_rps=-5, start_time=0.0)


def test_target_time_formula() -> None:
    scheduler = RateScheduler(target_rps=4, start_time=100.0)

    assert scheduler.target_time_for(0) == 100.0
    assert scheduler.target_time_for(4) == 101.0
    assert scheduler.target_time_for(8) == 102.0


@pytest.mark.asyncio
async def test_first_request_has_no_wait(clock: FakeClock) -> None:
    sleeper = ManualSleeper(clock)
    scheduler = RateScheduler(
        target_rps=10, start_time=clock.now, clock=clock, sleep=sleeper
    )

    await scheduler.wait_for_slot(0, asyncio.Event())

    assert sleeper.calls == []


@pytest.mark.asyncio
async def test_waits_until_scheduled_time(clock: FakeClock) -> None:
    sleeper = ManualSleeper(clock)
    scheduler = RateScheduler(
        target_rps=10, start_time=clock.now, clock=clock, sleep=sleeper, poll_interval=1.0
    )

    await scheduler.wait_for_slot(5, asyncio.Event())

    assert clock.now == pytest.approx(1000.5)
    assert sleeper.calls


@pytest.mark.asyncio
async def test_does_not_exceed_target_rate_pacing(clock: FakeClock) -> None:
    sleeper = ManualSleeper(clock)
    scheduler = RateScheduler(
        target_rps=2, start_time=clock.now, clock=clock, sleep=sleeper, poll_interval=0.5
    )

    for index in range(4):
        await scheduler.wait_for_slot(index, asyncio.Event())

    # 4 requests at 2/sec must span at least 1.5s (indices 0..3 at 0, .5, 1, 1.5)
    assert clock.now - 1000.0 == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_stop_event_interrupts_wait(clock: FakeClock) -> None:
    stop_event = asyncio.Event()

    async def sleeper(seconds: float) -> None:
        clock.advance(seconds)
        stop_event.set()

    scheduler = RateScheduler(
        target_rps=1, start_time=clock.now, clock=clock, sleep=sleeper, poll_interval=0.01
    )

    await scheduler.wait_for_slot(100, stop_event)  # would need ~100s without the stop

    assert clock.now < 1001.0


@pytest.mark.asyncio
async def test_already_due_slot_returns_immediately(clock: FakeClock) -> None:
    sleeper = ManualSleeper(clock)
    clock.advance(10.0)
    scheduler = RateScheduler(
        target_rps=10, start_time=1000.0, clock=clock, sleep=sleeper
    )

    await scheduler.wait_for_slot(0, asyncio.Event())

    assert sleeper.calls == []
