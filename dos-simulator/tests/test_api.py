"""HTTPX integration tests for the simulation REST API.

The simulator's outbound HTTP calls are routed to an in-process fake target
app via httpx.ASGITransport, so these tests never touch a real network.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.main import create_app
from app.simulation.manager import SimulationManager
from app.storage import ExperimentRepository
from tests.conftest import make_target_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    target_transport = httpx.ASGITransport(app=make_target_app())
    manager = SimulationManager(
        repository=ExperimentRepository(":memory:"),
        settings=Settings(),
        transport=target_transport,
    )
    app = create_app(manager=manager)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://simulator"
    ) as http_client:
        yield http_client
    await manager.shutdown()


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "target_url": "http://target",
        "endpoint": "/data",
        "method": "GET",
        "total_requests": 20,
        "target_rps": 200,
        "concurrency": 5,
        "timeout": 2,
    }
    payload.update(overrides)
    return payload


async def wait_until_terminal(
    client: httpx.AsyncClient, simulation_id: str, timeout: float = 5.0
) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        response = await client.get(f"/simulations/{simulation_id}")
        body = response.json()
        if body["status"] in ("COMPLETED", "STOPPED", "FAILED"):
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"Simulation did not finish in time: {body}")
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_create_simulation_returns_running_id(client: httpx.AsyncClient) -> None:
    response = await client.post("/simulations", json=valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["simulation_id"]


@pytest.mark.asyncio
async def test_invalid_configuration_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/simulations", json=valid_payload(total_requests=0))

    assert response.status_code == 422
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_invalid_target_url_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/simulations", json=valid_payload(target_url="not-a-url")
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_above_safety_limits_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/simulations", json=valid_payload(total_requests=10_000_000)
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_status_for_unknown_simulation_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/simulations/does-not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_simulation_runs_to_completion(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/simulations", json=valid_payload(total_requests=15, target_rps=500)
    )
    simulation_id = created.json()["simulation_id"]

    final = await wait_until_terminal(client, simulation_id)

    assert final["status"] == "COMPLETED"
    assert final["completed_requests"] == 15
    assert final["successful_requests"] == 15
    assert final["target_rps"] == 500


@pytest.mark.asyncio
async def test_stop_simulation(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/simulations",
        json=valid_payload(total_requests=100_000, target_rps=50, concurrency=5),
    )
    simulation_id = created.json()["simulation_id"]
    await asyncio.sleep(0.1)

    response = await client.post(f"/simulations/{simulation_id}/stop")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "STOPPED"
    assert body["completed_requests"] < 100_000


@pytest.mark.asyncio
async def test_stopping_a_finished_simulation_returns_409(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/simulations", json=valid_payload(total_requests=5, target_rps=500)
    )
    simulation_id = created.json()["simulation_id"]
    await wait_until_terminal(client, simulation_id)

    response = await client.post(f"/simulations/{simulation_id}/stop")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_stopping_unknown_simulation_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/simulations/does-not-exist/stop")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_history_contains_completed_simulation(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/simulations", json=valid_payload(total_requests=5, target_rps=500)
    )
    simulation_id = created.json()["simulation_id"]
    await wait_until_terminal(client, simulation_id)
    await asyncio.sleep(0.05)  # let the persistence task finish

    history = await client.get("/simulations/history")
    assert history.status_code == 200
    ids = [item["simulation_id"] for item in history.json()]
    assert simulation_id in ids

    item = await client.get(f"/simulations/history/{simulation_id}")
    assert item.status_code == 200
    assert item.json()["status"] == "COMPLETED"
    assert item.json()["successful_requests"] == 5


@pytest.mark.asyncio
async def test_history_item_not_found_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/simulations/history/does-not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rate_limited_target_is_reflected_in_status(
    client: httpx.AsyncClient,
) -> None:
    # Build a second app wired to a target that rate-limits after 3 requests.
    target_transport = httpx.ASGITransport(app=make_target_app(rate_limit_after=3))
    manager = SimulationManager(
        repository=ExperimentRepository(":memory:"),
        settings=Settings(),
        transport=target_transport,
    )
    app = create_app(manager=manager)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://simulator"
    ) as local_client:
        created = await local_client.post(
            "/simulations",
            json=valid_payload(total_requests=10, target_rps=500, concurrency=1),
        )
        simulation_id = created.json()["simulation_id"]
        final = await wait_until_terminal(local_client, simulation_id)
    await manager.shutdown()

    assert final["successful_requests"] == 3
    assert final["rate_limited_requests"] == 7


@pytest.mark.asyncio
async def test_unhandled_error_is_sanitized(client: httpx.AsyncClient) -> None:
    response = await client.post("/simulations", json={"not": "a valid config"})

    assert response.status_code == 422
    assert "Traceback" not in response.text
