"""Tests for SimulationEngine: lifecycle, concurrency, totals, failure handling.

The engine's HTTPX client is always given an httpx.MockTransport here, so no
test ever opens a real socket or sends unrestricted traffic anywhere.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import Settings
from app.models.simulation import SimulationConfig, SimulationStatus
from app.simulation.engine import SimulationAlreadyFinishedError, SimulationEngine


def make_config(**overrides: object) -> SimulationConfig:
    base: dict[str, object] = {
        "target_url": "http://testserver",
        "endpoint": "/data",
        "method": "GET",
        "total_requests": 10,
        "target_rps": 1000,
        "concurrency": 4,
        "timeout": 1.0,
    }
    base.update(overrides)
    return SimulationConfig(**base)


@pytest.mark.asyncio
async def test_completes_and_counts_every_request() -> None:
    config = make_config(total_requests=20, concurrency=5)
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    engine = SimulationEngine("sim1", config, Settings(), transport=transport)

    await engine.run()

    assert engine.status == SimulationStatus.COMPLETED
    snapshot = engine.status_response()
    assert snapshot.completed_requests == 20
    assert snapshot.successful_requests == 20
    assert snapshot.failed_requests == 0


@pytest.mark.asyncio
async def test_never_exceeds_configured_concurrency() -> None:
    config = make_config(total_requests=40, concurrency=5, target_rps=1000)
    in_flight = {"current": 0, "peak": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        in_flight["current"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
        await asyncio.sleep(0.01)
        in_flight["current"] -= 1
        return httpx.Response(200)

    engine = SimulationEngine(
        "sim2", config, Settings(), transport=httpx.MockTransport(handler)
    )

    await engine.run()

    assert in_flight["peak"] <= 5
    assert engine.status_response().completed_requests == 40


@pytest.mark.asyncio
async def test_stops_exactly_at_total_requests() -> None:
    config = make_config(total_requests=7, concurrency=3)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200)

    engine = SimulationEngine(
        "sim3", config, Settings(), transport=httpx.MockTransport(handler)
    )

    await engine.run()

    assert calls["count"] == 7
    assert engine.status_response().completed_requests == 7


@pytest.mark.asyncio
async def test_stop_is_graceful_and_bounds_total_sent() -> None:
    config = make_config(total_requests=100_000, concurrency=5, target_rps=50)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200)

    engine = SimulationEngine(
        "sim4", config, Settings(), transport=httpx.MockTransport(handler)
    )
    run_task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.1)

    await engine.stop()
    await run_task

    assert engine.status == SimulationStatus.STOPPED
    assert calls["count"] < 100_000


@pytest.mark.asyncio
async def test_stopping_twice_raises() -> None:
    config = make_config(total_requests=100_000, concurrency=2, target_rps=10)
    engine = SimulationEngine(
        "sim5",
        config,
        Settings(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    run_task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.05)

    await engine.stop()
    await run_task

    with pytest.raises(SimulationAlreadyFinishedError):
        await engine.stop()


@pytest.mark.asyncio
async def test_stop_before_run_sets_stopping_state() -> None:
    config = make_config()
    engine = SimulationEngine("sim5b", config, Settings())

    # CREATED is not terminal, so a stop request before run() is accepted.
    await engine.stop()

    assert engine.status == SimulationStatus.STOPPING


@pytest.mark.asyncio
async def test_classifies_rate_limited_responses() -> None:
    config = make_config(total_requests=10, concurrency=2)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] <= 4:
            return httpx.Response(200)
        return httpx.Response(429)

    engine = SimulationEngine(
        "sim6", config, Settings(), transport=httpx.MockTransport(handler)
    )
    await engine.run()

    snapshot = engine.status_response()
    assert snapshot.successful_requests == 4
    assert snapshot.rate_limited_requests == 6
    assert snapshot.completed_requests == 10


@pytest.mark.asyncio
async def test_handles_mixed_outcomes_including_errors() -> None:
    config = make_config(total_requests=5, concurrency=1, target_rps=1000)
    responses = iter(
        [
            httpx.Response(200),
            httpx.Response(429),
            httpx.Response(404),
            httpx.Response(500),
            httpx.Response(200),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    engine = SimulationEngine(
        "sim7", config, Settings(), transport=httpx.MockTransport(handler)
    )
    await engine.run()

    snapshot = engine.status_response()
    assert snapshot.successful_requests == 2
    assert snapshot.rate_limited_requests == 1
    assert snapshot.client_errors == 1
    assert snapshot.server_errors == 1
    assert snapshot.failed_requests == 2


@pytest.mark.asyncio
async def test_does_not_run_indefinitely() -> None:
    config = make_config(total_requests=30, concurrency=10, target_rps=1000)
    engine = SimulationEngine(
        "sim8",
        config,
        Settings(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )

    await asyncio.wait_for(engine.run(), timeout=5.0)

    assert engine.status == SimulationStatus.COMPLETED


@pytest.mark.asyncio
async def test_latency_is_measured_per_request() -> None:
    config = make_config(total_requests=3, concurrency=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    engine = SimulationEngine(
        "sim9", config, Settings(), transport=httpx.MockTransport(handler)
    )
    await engine.run()

    snapshot = engine.status_response()
    assert snapshot.average_latency_ms >= 0
    assert snapshot.maximum_latency_ms >= snapshot.minimum_latency_ms


@pytest.mark.asyncio
async def test_experiment_summary_reflects_the_run() -> None:
    config = make_config(total_requests=6, concurrency=2)
    engine = SimulationEngine(
        "sim10",
        config,
        Settings(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    await engine.run()

    summary = engine.to_experiment_summary()
    assert summary.simulation_id == "sim10"
    assert summary.successful_requests == 6
    assert summary.status == SimulationStatus.COMPLETED
    assert summary.target_url == "http://testserver"
