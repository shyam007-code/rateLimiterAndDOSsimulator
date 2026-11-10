"""Broadcasts periodic simulation snapshots to connected WebSocket clients.

Requests are never streamed one-by-one -- a single background task per
simulation polls its engine at a fixed rate and pushes one aggregate
snapshot to every connected client, regardless of how many requests
completed in between.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.config import Settings
from app.config import settings as default_settings
from app.models.simulation import SimulationSnapshotMessage
from app.simulation.engine import SimulationEngine

logger = logging.getLogger(__name__)


class SimulationHub:
    """Owns one broadcaster task per actively-watched simulation."""

    def __init__(self, settings: Settings = default_settings) -> None:
        self._settings = settings
        self._connections: dict[str, set[WebSocket]] = {}
        self._broadcasters: dict[str, asyncio.Task[None]] = {}

    async def stream(
        self, simulation_id: str, engine: SimulationEngine, websocket: WebSocket
    ) -> None:
        """Accept one client and keep it updated until it disconnects or the
        simulation ends."""
        await websocket.accept()
        connections = self._connections.setdefault(simulation_id, set())
        connections.add(websocket)
        existing = self._broadcasters.get(simulation_id)
        if existing is None or existing.done():
            self._broadcasters[simulation_id] = asyncio.create_task(
                self._broadcast_loop(simulation_id, engine)
            )
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            connections.discard(websocket)

    async def _broadcast_loop(self, simulation_id: str, engine: SimulationEngine) -> None:
        interval = 1.0 / self._settings.WEBSOCKET_UPDATES_PER_SECOND
        try:
            while True:
                await self._send_to_all(simulation_id, engine.snapshot_message())
                if engine.is_terminal:
                    return
                await asyncio.sleep(interval)
        finally:
            await self._close_all(simulation_id)

    async def _send_to_all(
        self, simulation_id: str, message: SimulationSnapshotMessage
    ) -> None:
        payload = message.model_dump(mode="json")
        for websocket in list(self._connections.get(simulation_id, ())):
            if websocket.application_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_json(payload)
                except Exception:
                    logger.debug("Dropping disconnected websocket for %s", simulation_id)
                    self._connections.get(simulation_id, set()).discard(websocket)

    async def _close_all(self, simulation_id: str) -> None:
        for websocket in list(self._connections.get(simulation_id, ())):
            try:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.close()
            except Exception:
                pass
        self._connections.pop(simulation_id, None)
