"""WebSocket endpoint streaming periodic simulation snapshots."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.simulation.manager import SimulationManager, SimulationNotFoundError
from app.websocket.manager import SimulationHub

router = APIRouter()


@router.websocket("/simulations/{simulation_id}/stream")
async def simulation_stream(websocket: WebSocket, simulation_id: str) -> None:
    """Stream periodic aggregate snapshots for one simulation.

    Closes with code 4404 immediately if the simulation id is unknown.
    """
    manager: SimulationManager = websocket.app.state.simulation_manager
    hub: SimulationHub = websocket.app.state.simulation_hub
    try:
        engine = manager.get(simulation_id)
    except SimulationNotFoundError:
        await websocket.close(code=4404)
        return
    try:
        await hub.stream(simulation_id, engine, websocket)
    except WebSocketDisconnect:
        pass
