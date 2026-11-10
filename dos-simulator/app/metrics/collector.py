"""Aggregate, in-memory metrics for one simulation run.

Only counters and latency aggregates are kept -- individual requests are
never stored -- so memory use stays constant no matter how many requests are
sent.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.http.client import RequestOutcome

Clock = Callable[[], float]

_CATEGORY_ATTRS: dict[str, str] = {
    "successful": "successful",
    "rate_limited": "rate_limited",
    "client_error": "client_errors",
    "server_error": "server_errors",
    "timeout": "timeouts",
    "network_error": "network_errors",
    "other": "other_errors",
}


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Immutable point-in-time view of every counter and latency stat."""

    successful: int
    rate_limited: int
    client_errors: int
    server_errors: int
    timeouts: int
    network_errors: int
    other_errors: int
    average_latency: float
    minimum_latency: float
    maximum_latency: float
    current_rps: float

    @property
    def completed_requests(self) -> int:
        """Total requests that have finished, in any category."""
        return (
            self.successful
            + self.rate_limited
            + self.client_errors
            + self.server_errors
            + self.timeouts
            + self.network_errors
            + self.other_errors
        )

    @property
    def failed_requests(self) -> int:
        """Completed requests that were not successful or rate-limited."""
        return (
            self.client_errors
            + self.server_errors
            + self.timeouts
            + self.network_errors
            + self.other_errors
        )


class MetricsCollector:
    """Counts request outcomes and tracks latency, without storing requests.

    Not thread-safe by design: it is only ever touched from the single event
    loop thread that runs the simulation's workers, and every update
    completes with no ``await`` in between, so there is no window for another
    coroutine to observe a partial update.
    """

    def __init__(
        self, clock: Clock = time.monotonic, window_seconds: float = 1.0
    ) -> None:
        self._clock = clock
        self._window_seconds = window_seconds
        self.successful = 0
        self.rate_limited = 0
        self.client_errors = 0
        self.server_errors = 0
        self.timeouts = 0
        self.network_errors = 0
        self.other_errors = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._latency_min = math.inf
        self._latency_max = 0.0
        self._recent_completions: deque[float] = deque()

    def record(self, outcome: RequestOutcome) -> None:
        """Record one completed request's classification and latency."""
        attr = _CATEGORY_ATTRS.get(outcome.category, "other_errors")
        setattr(self, attr, getattr(self, attr) + 1)
        self._record_latency(outcome.latency_seconds)
        self._record_completion_time(self._clock())

    def _record_latency(self, latency: float) -> None:
        self._latency_sum += latency
        self._latency_count += 1
        if latency < self._latency_min:
            self._latency_min = latency
        if latency > self._latency_max:
            self._latency_max = latency

    def _record_completion_time(self, now: float) -> None:
        self._recent_completions.append(now)
        self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._recent_completions and self._recent_completions[0] < cutoff:
            self._recent_completions.popleft()

    def snapshot(self) -> MetricsSnapshot:
        """Return a consistent snapshot of every counter and latency stat."""
        average_latency = (
            self._latency_sum / self._latency_count if self._latency_count else 0.0
        )
        minimum_latency = self._latency_min if self._latency_count else 0.0
        # Re-trim using the current clock so an idle gap is reflected even if
        # no new request has arrived since to trigger a trim.
        self._trim(self._clock())
        current_rps = len(self._recent_completions) / self._window_seconds
        return MetricsSnapshot(
            successful=self.successful,
            rate_limited=self.rate_limited,
            client_errors=self.client_errors,
            server_errors=self.server_errors,
            timeouts=self.timeouts,
            network_errors=self.network_errors,
            other_errors=self.other_errors,
            average_latency=average_latency,
            minimum_latency=minimum_latency,
            maximum_latency=self._latency_max,
            current_rps=current_rps,
        )
