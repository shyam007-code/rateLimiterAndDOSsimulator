"""Coordinates one simulation run: HTTP client, workers, scheduling, metrics."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.metrics.collector import MetricsCollector
from app.models.simulation import (
    ExperimentSummary,
    SimulationConfig,
    SimulationSnapshotMessage,
    SimulationStatus,
    SimulationStatusResponse,
)
from app.simulation.scheduler import RateScheduler
from app.simulation.worker import IndexAllocator, WorkerContext, worker_loop

Clock = Callable[[], float]


class SimulationAlreadyFinishedError(RuntimeError):
    """Raised when ``stop()`` is called on a simulation that already ended."""


class SimulationEngine:
    """Owns the full lifecycle of a single simulation run.

    The engine coordinates configuration, the worker pool, the shared HTTPX
    client, rate scheduling and metrics. It never runs longer than
    ``config.total_requests`` permits, and ``stop()`` ends it early and
    safely.
    """

    def __init__(
        self,
        simulation_id: str,
        config: SimulationConfig,
        settings: Settings,
        clock: Clock = time.monotonic,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.id = simulation_id
        self.config = config
        self.created_at = datetime.now(UTC)
        self.error: str | None = None
        self.status = SimulationStatus.CREATED
        self.metrics = MetricsCollector(clock=clock)
        self._settings = settings
        self._clock = clock
        self._transport = transport
        self._stop_event = asyncio.Event()
        self._start_time: float | None = None
        self._end_time: float | None = None

    @property
    def is_terminal(self) -> bool:
        """``True`` once the simulation has reached a final state."""
        return self.status in (
            SimulationStatus.COMPLETED,
            SimulationStatus.STOPPED,
            SimulationStatus.FAILED,
        )

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since the run started (or 0 before it has)."""
        if self._start_time is None:
            return 0.0
        end = self._end_time if self._end_time is not None else self._clock()
        return max(end - self._start_time, 0.0)

    async def run(self) -> None:
        """Execute the simulation to completion, or until ``stop()`` is called.

        Always closes the HTTPX client and always leaves ``status`` in a
        terminal state (``COMPLETED``, ``STOPPED`` or ``FAILED``), even if an
        unexpected error occurs.
        """
        self.status = SimulationStatus.RUNNING
        self._start_time = self._clock()
        allocator = IndexAllocator(total=self.config.total_requests)
        scheduler = RateScheduler(
            target_rps=self.config.target_rps,
            start_time=self._start_time,
            clock=self._clock,
        )
        limits = httpx.Limits(
            max_connections=self.config.concurrency * 2,
            max_keepalive_connections=self.config.concurrency,
        )
        timeout = httpx.Timeout(self.config.timeout)
        try:
            async with httpx.AsyncClient(
                limits=limits, timeout=timeout, transport=self._transport
            ) as client:
                context = WorkerContext(
                    client=client,
                    method=self.config.method,
                    url=self.config.full_url,
                    timeout=self.config.timeout,
                    allocator=allocator,
                    scheduler=scheduler,
                    metrics=self.metrics,
                    stop_event=self._stop_event,
                )
                workers = [
                    asyncio.create_task(worker_loop(context))
                    for _ in range(self.config.concurrency)
                ]
                await asyncio.gather(*workers)
            self.status = (
                SimulationStatus.STOPPED
                if self._stop_event.is_set()
                else SimulationStatus.COMPLETED
            )
        except Exception as exc:  # noqa: BLE001 - isolate failures per simulation
            self.error = str(exc)
            self.status = SimulationStatus.FAILED
        finally:
            self._end_time = self._clock()

    async def stop(self) -> None:
        """Request a graceful stop.

        Raises:
            SimulationAlreadyFinishedError: If the simulation already reached
                a terminal state.
        """
        if self.is_terminal:
            raise SimulationAlreadyFinishedError(
                f"Simulation {self.id} already finished with status {self.status}"
            )
        self.status = SimulationStatus.STOPPING
        self._stop_event.set()

    def status_response(self) -> SimulationStatusResponse:
        """Build the full REST status payload from the current metrics."""
        snapshot = self.metrics.snapshot()
        elapsed = self.elapsed_seconds
        average_rps = snapshot.completed_requests / elapsed if elapsed > 0 else 0.0
        return SimulationStatusResponse(
            simulation_id=self.id,
            status=self.status,
            target_url=self.config.target_url,
            endpoint=self.config.endpoint,
            total_requests=self.config.total_requests,
            completed_requests=snapshot.completed_requests,
            successful_requests=snapshot.successful,
            rate_limited_requests=snapshot.rate_limited,
            client_errors=snapshot.client_errors,
            server_errors=snapshot.server_errors,
            timeouts=snapshot.timeouts,
            network_errors=snapshot.network_errors,
            other_errors=snapshot.other_errors,
            failed_requests=snapshot.failed_requests,
            target_rps=self.config.target_rps,
            current_rps=round(snapshot.current_rps, 3),
            average_rps=round(average_rps, 3),
            average_latency_ms=round(snapshot.average_latency * 1000, 3),
            minimum_latency_ms=round(snapshot.minimum_latency * 1000, 3),
            maximum_latency_ms=round(snapshot.maximum_latency * 1000, 3),
            elapsed_seconds=round(elapsed, 3),
        )

    def snapshot_message(self) -> SimulationSnapshotMessage:
        """Build the compact payload sent over the WebSocket stream."""
        snapshot = self.metrics.snapshot()
        return SimulationSnapshotMessage(
            simulation_id=self.id,
            status=self.status,
            total_requests=self.config.total_requests,
            completed_requests=snapshot.completed_requests,
            successful_requests=snapshot.successful,
            rate_limited_requests=snapshot.rate_limited,
            failed_requests=snapshot.failed_requests,
            current_rps=round(snapshot.current_rps, 3),
            average_latency_ms=round(snapshot.average_latency * 1000, 3),
            elapsed_seconds=round(self.elapsed_seconds, 3),
        )

    def to_experiment_summary(self) -> ExperimentSummary:
        """Build the aggregate record persisted to SQLite on completion."""
        snapshot = self.metrics.snapshot()
        elapsed = self.elapsed_seconds
        actual_rps = snapshot.completed_requests / elapsed if elapsed > 0 else 0.0
        return ExperimentSummary(
            simulation_id=self.id,
            created_at=self.created_at,
            target_url=self.config.target_url,
            endpoint=self.config.endpoint,
            total_requests=self.config.total_requests,
            successful_requests=snapshot.successful,
            rate_limited_requests=snapshot.rate_limited,
            failed_requests=snapshot.failed_requests,
            target_rps=self.config.target_rps,
            actual_rps=round(actual_rps, 3),
            average_latency_ms=round(snapshot.average_latency * 1000, 3),
            duration_seconds=round(elapsed, 3),
            status=self.status,
        )
