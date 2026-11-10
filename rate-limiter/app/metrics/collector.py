"""Concurrency-safe, in-memory request counters."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Immutable point-in-time view of the counters."""

    total_requests: int
    allowed_requests: int
    rejected_requests: int


class MetricsCollector:
    """Counts allowed and rejected requests without storing individual ones.

    ``total_requests`` is derived from the other two counters, so the
    invariant ``total == allowed + rejected`` always holds.
    """

    def __init__(self) -> None:
        self._allowed = 0
        self._rejected = 0
        self._lock = asyncio.Lock()

    async def record(self, *, allowed: bool) -> None:
        """Record the outcome of a single request."""
        async with self._lock:
            if allowed:
                self._allowed += 1
            else:
                self._rejected += 1

    async def snapshot(self) -> MetricsSnapshot:
        """Return a consistent copy of the counters."""
        async with self._lock:
            return MetricsSnapshot(
                total_requests=self._allowed + self._rejected,
                allowed_requests=self._allowed,
                rejected_requests=self._rejected,
            )
