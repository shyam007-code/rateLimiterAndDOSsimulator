"""Unit tests for MetricsCollector."""

from __future__ import annotations

import pytest

from app.http.client import RequestOutcome
from app.metrics.collector import MetricsCollector
from tests.conftest import FakeClock

_STATUS_FOR_CATEGORY = {
    "successful": 200,
    "rate_limited": 429,
    "client_error": 404,
    "server_error": 500,
}


def make_outcome(category: str, latency: float = 0.01) -> RequestOutcome:
    return RequestOutcome(_STATUS_FOR_CATEGORY.get(category), category, latency, None)


def test_successful_counting() -> None:
    metrics = MetricsCollector()
    metrics.record(make_outcome("successful"))
    metrics.record(make_outcome("successful"))

    snapshot = metrics.snapshot()
    assert snapshot.successful == 2
    assert snapshot.completed_requests == 2
    assert snapshot.failed_requests == 0


def test_rate_limited_counting() -> None:
    metrics = MetricsCollector()
    metrics.record(make_outcome("rate_limited"))
    metrics.record(make_outcome("rate_limited"))
    metrics.record(make_outcome("successful"))

    snapshot = metrics.snapshot()
    assert snapshot.rate_limited == 2
    assert snapshot.completed_requests == 3


@pytest.mark.parametrize(
    ("category", "attr"),
    [
        ("client_error", "client_errors"),
        ("server_error", "server_errors"),
        ("timeout", "timeouts"),
        ("network_error", "network_errors"),
        ("other", "other_errors"),
    ],
)
def test_error_counting(category: str, attr: str) -> None:
    metrics = MetricsCollector()
    metrics.record(make_outcome(category))

    snapshot = metrics.snapshot()
    assert getattr(snapshot, attr) == 1
    assert snapshot.failed_requests == 1
    assert snapshot.completed_requests == 1


def test_latency_calculation() -> None:
    metrics = MetricsCollector()
    for latency in (0.01, 0.02, 0.03):
        metrics.record(make_outcome("successful", latency))

    snapshot = metrics.snapshot()
    assert snapshot.average_latency == pytest.approx(0.02)
    assert snapshot.minimum_latency == pytest.approx(0.01)
    assert snapshot.maximum_latency == pytest.approx(0.03)


def test_snapshot_with_no_requests() -> None:
    metrics = MetricsCollector()

    snapshot = metrics.snapshot()

    assert snapshot.completed_requests == 0
    assert snapshot.failed_requests == 0
    assert snapshot.average_latency == 0.0
    assert snapshot.minimum_latency == 0.0
    assert snapshot.maximum_latency == 0.0
    assert snapshot.current_rps == 0.0


def test_current_rps_uses_recent_window() -> None:
    clock = FakeClock()
    metrics = MetricsCollector(clock=clock, window_seconds=1.0)

    for _ in range(5):
        metrics.record(make_outcome("successful"))
    assert metrics.snapshot().current_rps == pytest.approx(5.0)

    clock.advance(2.0)  # older completions fall out of the 1s window
    assert metrics.snapshot().current_rps == pytest.approx(0.0)

    metrics.record(make_outcome("successful"))
    assert metrics.snapshot().current_rps == pytest.approx(1.0)


def test_counters_do_not_store_individual_requests() -> None:
    """The collector exposes only aggregate counters, never a request log."""
    metrics = MetricsCollector()
    for _ in range(1000):
        metrics.record(make_outcome("successful"))

    public_attrs = {
        name
        for name in vars(metrics)
        if not name.startswith("_")
    }
    assert "requests" not in public_attrs
    assert "log" not in public_attrs
    assert metrics.successful == 1000
