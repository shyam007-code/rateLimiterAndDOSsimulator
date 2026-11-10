"""Worker coroutine that drives one lane of concurrent, paced requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from app.http.client import send_request
from app.metrics.collector import MetricsCollector
from app.simulation.scheduler import RateScheduler


@dataclass(slots=True)
class IndexAllocator:
    """Hands out sequential request indices up to ``total``, each exactly once."""

    total: int
    _next: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def next(self, stop_event: asyncio.Event) -> int | None:
        """Claim the next index, or ``None`` if exhausted or stopped."""
        async with self._lock:
            if stop_event.is_set() or self._next >= self.total:
                return None
            index = self._next
            self._next += 1
            return index


@dataclass(slots=True)
class WorkerContext:
    """Shared, read-mostly state handed to every worker in a simulation."""

    client: httpx.AsyncClient
    method: str
    url: str
    timeout: float
    allocator: IndexAllocator
    scheduler: RateScheduler
    metrics: MetricsCollector
    stop_event: asyncio.Event


async def worker_loop(ctx: WorkerContext) -> None:
    """Claim indices and perform paced requests until none remain or stopped.

    Each worker ever has at most one request in flight, so the number of
    concurrently running ``worker_loop`` tasks is the hard bound on
    concurrency.
    """
    while True:
        index = await ctx.allocator.next(ctx.stop_event)
        if index is None:
            return
        await ctx.scheduler.wait_for_slot(index, ctx.stop_event)
        if ctx.stop_event.is_set():
            return
        outcome = await send_request(ctx.client, ctx.method, ctx.url, ctx.timeout)
        ctx.metrics.record(outcome)
