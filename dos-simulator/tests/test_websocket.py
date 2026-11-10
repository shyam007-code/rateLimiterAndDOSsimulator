"""Tests for the simulation WebSocket stream.

Uses Starlette's synchronous TestClient (the standard way to exercise
WebSocket endpoints), with the simulator's outbound calls routed to an
in-process fake target via ASGITransport -- no real network involved.

Each test opens the client with ``with TestClient(app) as client:``. That
keeps one event loop alive for the whole block, so the background task
started by ``POST /simulations`` is the same task later observed by the
WebSocket stream, instead of being torn down between separate event loops.
"""

from __future__ import annotations

import httpx
from starlette.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.simulation.manager import SimulationManager
from app.storage import ExperimentRepository
from app.websocket.manager import SimulationHub
from tests.conftest import make_target_app


def build_app(ws_hz: float = 50.0):
    target_transport = httpx.ASGITransport(app=make_target_app())
    settings = Settings(WEBSOCKET_UPDATES_PER_SECOND=ws_hz)
    manager = SimulationManager(
        repository=ExperimentRepository(":memory:"),
        settings=settings,
        transport=target_transport,
    )
    hub = SimulationHub(settings)
    return create_app(manager=manager, hub=hub)


def start_simulation(client: TestClient, **overrides: object) -> str:
    payload: dict[str, object] = {
        "target_url": "http://target",
        "endpoint": "/data",
        "method": "GET",
        "total_requests": 10,
        "target_rps": 200,
        "concurrency": 3,
        "timeout": 2,
    }
    payload.update(overrides)
    response = client.post("/simulations", json=payload)
    return response.json()["simulation_id"]


def test_stream_delivers_periodic_snapshots_and_closes() -> None:
    with TestClient(build_app()) as client:
        simulation_id = start_simulation(client)

        messages = []
        with client.websocket_connect(
            f"/simulations/{simulation_id}/stream"
        ) as websocket:
            while True:
                message = websocket.receive_json()
                messages.append(message)
                if message["status"] in ("COMPLETED", "STOPPED", "FAILED"):
                    break

    assert messages
    assert messages[0]["simulation_id"] == simulation_id
    assert messages[-1]["status"] == "COMPLETED"
    assert messages[-1]["completed_requests"] == 10
    assert messages[-1]["successful_requests"] == 10


def test_stream_message_shape() -> None:
    with TestClient(build_app()) as client:
        simulation_id = start_simulation(client, total_requests=5)

        with client.websocket_connect(
            f"/simulations/{simulation_id}/stream"
        ) as websocket:
            message = websocket.receive_json()

    expected_keys = {
        "simulation_id",
        "status",
        "total_requests",
        "completed_requests",
        "successful_requests",
        "rate_limited_requests",
        "failed_requests",
        "current_rps",
        "average_latency_ms",
        "elapsed_seconds",
    }
    assert expected_keys.issubset(message.keys())


def test_connecting_after_completion_sends_final_snapshot_immediately() -> None:
    with TestClient(build_app()) as client:
        simulation_id = start_simulation(client, total_requests=3, target_rps=500)

        # Drain a first connection until the simulation is done.
        with client.websocket_connect(
            f"/simulations/{simulation_id}/stream"
        ) as websocket:
            while True:
                message = websocket.receive_json()
                if message["status"] in ("COMPLETED", "STOPPED", "FAILED"):
                    break

        # A second, later connection should immediately get the final snapshot.
        with client.websocket_connect(
            f"/simulations/{simulation_id}/stream"
        ) as websocket:
            message = websocket.receive_json()

    assert message["status"] == "COMPLETED"
    assert message["completed_requests"] == 3


def test_stream_for_unknown_simulation_closes_immediately() -> None:
    from starlette.websockets import WebSocketDisconnect

    with TestClient(build_app()) as client:
        raised = False
        try:
            with client.websocket_connect("/simulations/does-not-exist/stream"):
                pass
        except WebSocketDisconnect as exc:
            raised = True
            assert exc.code == 4404

    assert raised
