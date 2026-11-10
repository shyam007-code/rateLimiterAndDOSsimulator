"""Creates, tracks and tears down simulations; persists completed summaries."""

from __future__ import annotations

import asyncio
import secrets

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.models.simulation import ExperimentSummary, SimulationConfig, SimulationStatus
from app.simulation.engine import SimulationEngine
from app.storage import ExperimentRepository


class SimulationNotFoundError(KeyError):
    """Raised when an unknown simulation id is requested."""


class SimulationManager:
    """In-memory registry of simulation engines plus the completed-run archive."""

    def __init__(
        self,
        repository: ExperimentRepository,
        settings: Settings = default_settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._transport = transport
        self._engines: dict[str, SimulationEngine] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def _new_id(self) -> str:
        candidate = secrets.token_hex(4)
        while candidate in self._engines:
            candidate = secrets.token_hex(4)
        return candidate

    def create(self, config: SimulationConfig) -> SimulationEngine:
        """Create a simulation and start it as a background task.

        The returned engine's ``status`` is already ``RUNNING``: the run has
        been scheduled on the event loop even though its worker tasks have
        not necessarily executed their first request yet.
        """
        simulation_id = self._new_id()
        engine = SimulationEngine(
            simulation_id, config, self._settings, transport=self._transport
        )
        engine.status = SimulationStatus.RUNNING
        self._engines[simulation_id] = engine
        self._tasks[simulation_id] = asyncio.create_task(self._run_and_persist(engine))
        return engine

    async def _run_and_persist(self, engine: SimulationEngine) -> None:
        await engine.run()
        await self._repository.save(engine.to_experiment_summary())

    def get(self, simulation_id: str) -> SimulationEngine:
        """Return the engine for ``simulation_id``.

        Raises:
            SimulationNotFoundError: If no such simulation exists.
        """
        try:
            return self._engines[simulation_id]
        except KeyError as exc:
            raise SimulationNotFoundError(simulation_id) from exc

    async def stop(self, simulation_id: str) -> SimulationEngine:
        """Stop a running simulation and wait for it to finish tearing down.

        Raises:
            SimulationNotFoundError: If no such simulation exists.
            SimulationAlreadyFinishedError: If it already reached a terminal
                state.
        """
        engine = self.get(simulation_id)
        await engine.stop()
        task = self._tasks.get(simulation_id)
        if task is not None:
            await task
        return engine

    async def history(self, limit: int = 100) -> list[ExperimentSummary]:
        """Return the most recent completed experiments."""
        return await self._repository.list_recent(limit)

    async def history_item(self, simulation_id: str) -> ExperimentSummary:
        """Return one completed experiment's summary.

        Raises:
            SimulationNotFoundError: If no completed experiment has that id.
        """
        item = await self._repository.get(simulation_id)
        if item is None:
            raise SimulationNotFoundError(simulation_id)
        return item

    async def shutdown(self) -> None:
        """Stop every still-running simulation and wait for its task.

        Called on application shutdown so no orphaned tasks or open HTTPX
        clients are left behind.
        """
        for engine in list(self._engines.values()):
            if not engine.is_terminal:
                try:
                    await engine.stop()
                except Exception:  # noqa: BLE001 - best-effort on shutdown
                    pass
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
