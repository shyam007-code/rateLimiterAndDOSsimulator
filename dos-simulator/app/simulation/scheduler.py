"""Paces outgoing requests toward a target rate.

This is a request-dispatch scheduler for the simulator's own outbound load;
it has no relationship to, and does not implement, the rate limiter being
tested.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class RateScheduler:
    """Computes and waits for each request's scheduled dispatch time.

    Request ``index`` (0-based) is scheduled at
    ``start_time + index / target_rps``. Waiting happens in short slices so a
    stop request takes effect within one slice instead of oversleeping.
    """

    def __init__(
        self,
        target_rps: float,
        start_time: float,
        clock: Clock = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
        poll_interval: float = 0.05,
    ) -> None:
        if target_rps <= 0:
            raise ValueError("target_rps must be positive")
        self._target_rps = target_rps
        self._start_time = start_time
        self._clock = clock
        self._sleep = sleep
        self._poll_interval = poll_interval

    def target_time_for(self, index: int) -> float:
        """The monotonic time at which request ``index`` should be sent."""
        return self._start_time + index / self._target_rps

    async def wait_for_slot(self, index: int, stop_event: asyncio.Event) -> None:
        """Sleep until ``index``'s scheduled time, or return early if stopped."""
        target = self.target_time_for(index)
        while True:
            remaining = target - self._clock()
            if remaining <= 0 or stop_event.is_set():
                return
            await self._sleep(min(remaining, self._poll_interval))
