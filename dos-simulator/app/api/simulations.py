"""REST endpoints for creating, stopping and inspecting simulations.

Route order matters: the literal ``/simulations/history`` paths are declared
before the dynamic ``/simulations/{simulation_id}`` path so a request for
``/simulations/history`` is never captured as a lookup for a simulation
literally named "history".
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.models.simulation import (
    ExperimentSummary,
    SimulationConfig,
    SimulationCreateResponse,
    SimulationStatusResponse,
)
from app.simulation.engine import SimulationAlreadyFinishedError
from app.simulation.manager import SimulationManager, SimulationNotFoundError

router = APIRouter(tags=["simulations"])


def get_manager(request: Request) -> SimulationManager:
    """Dependency returning the manager stored on ``app.state``."""
    manager: SimulationManager = request.app.state.simulation_manager
    return manager


ManagerDep = Annotated[SimulationManager, Depends(get_manager)]


@router.post("/simulations", response_model=SimulationCreateResponse, status_code=201)
async def create_simulation(
    config: SimulationConfig, manager: ManagerDep
) -> SimulationCreateResponse:
    """Validate the configuration, start the simulation, and return its id."""
    engine = manager.create(config)
    return SimulationCreateResponse(simulation_id=engine.id, status=engine.status)


@router.get("/simulations/history", response_model=list[ExperimentSummary])
async def list_history(manager: ManagerDep, limit: int = 100) -> list[ExperimentSummary]:
    """Return the most recently completed experiments."""
    return await manager.history(limit)


@router.get("/simulations/history/{simulation_id}", response_model=ExperimentSummary)
async def get_history_item(
    simulation_id: str, manager: ManagerDep
) -> ExperimentSummary:
    """Return one completed experiment's stored summary."""
    try:
        return await manager.history_item(simulation_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Simulation not found") from exc


@router.get("/simulations/{simulation_id}", response_model=SimulationStatusResponse)
async def get_simulation(
    simulation_id: str, manager: ManagerDep
) -> SimulationStatusResponse:
    """Return the current status and metrics of one simulation."""
    try:
        engine = manager.get(simulation_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Simulation not found") from exc
    return engine.status_response()


@router.post(
    "/simulations/{simulation_id}/stop", response_model=SimulationStatusResponse
)
async def stop_simulation(
    simulation_id: str, manager: ManagerDep
) -> SimulationStatusResponse:
    """Gracefully stop a running simulation."""
    try:
        engine = await manager.stop(simulation_id)
    except SimulationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Simulation not found") from exc
    except SimulationAlreadyFinishedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return engine.status_response()
