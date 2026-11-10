"""Minimal SQLite-backed storage for completed experiment summaries.

Only aggregate summaries are stored here -- never individual requests,
request bodies or credentials. All access runs off the event loop thread via
``asyncio.to_thread`` so file IO never blocks the simulator.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.models.simulation import ExperimentSummary, SimulationStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    target_url TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    total_requests INTEGER NOT NULL,
    successful_requests INTEGER NOT NULL,
    rate_limited_requests INTEGER NOT NULL,
    failed_requests INTEGER NOT NULL,
    target_rps REAL NOT NULL,
    actual_rps REAL NOT NULL,
    average_latency_ms REAL NOT NULL,
    duration_seconds REAL NOT NULL,
    status TEXT NOT NULL
);
"""


class ExperimentRepository:
    """Synchronous SQLite access, always invoked off the event loop thread."""

    def __init__(self, database_path: str) -> None:
        self._path = database_path
        # A plain ":memory:" database only exists for the lifetime of the
        # connection that created it -- opening a fresh connection per call
        # (as we do for a file path) would hand back a brand-new, empty
        # database every time. For in-memory mode we instead keep one
        # connection alive for the repository's whole lifetime and reuse it
        # for every operation.
        self._shared_memory_connection: sqlite3.Connection | None = None
        if self._path == ":memory:":
            connection = sqlite3.connect(self._path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            self._shared_memory_connection = connection
        else:
            parent = Path(self._path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(_SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection; commits on success, rolls back on error.

        Reuses the shared connection for in-memory mode; opens and closes a
        fresh connection per call for a file-backed database.
        """
        if self._shared_memory_connection is not None:
            connection = self._shared_memory_connection
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _save_sync(self, summary: ExperimentSummary) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO experiments (
                    id, created_at, target_url, endpoint, total_requests,
                    successful_requests, rate_limited_requests, failed_requests,
                    target_rps, actual_rps, average_latency_ms, duration_seconds,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.simulation_id,
                    summary.created_at.isoformat(),
                    summary.target_url,
                    summary.endpoint,
                    summary.total_requests,
                    summary.successful_requests,
                    summary.rate_limited_requests,
                    summary.failed_requests,
                    summary.target_rps,
                    summary.actual_rps,
                    summary.average_latency_ms,
                    summary.duration_seconds,
                    summary.status.value,
                ),
            )

    async def save(self, summary: ExperimentSummary) -> None:
        """Persist a completed experiment's summary."""
        await asyncio.to_thread(self._save_sync, summary)

    def _list_sync(self, limit: int) -> list[ExperimentSummary]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_summary(row) for row in rows]

    async def list_recent(self, limit: int = 100) -> list[ExperimentSummary]:
        """Return the most recently completed experiments."""
        return await asyncio.to_thread(self._list_sync, limit)

    def _get_sync(self, simulation_id: str) -> ExperimentSummary | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE id = ?", (simulation_id,)
            ).fetchone()
        return self._row_to_summary(row) if row else None

    async def get(self, simulation_id: str) -> ExperimentSummary | None:
        """Return one completed experiment's summary, or ``None``."""
        return await asyncio.to_thread(self._get_sync, simulation_id)

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> ExperimentSummary:
        return ExperimentSummary(
            simulation_id=row["id"],
            created_at=row["created_at"],
            target_url=row["target_url"],
            endpoint=row["endpoint"],
            total_requests=row["total_requests"],
            successful_requests=row["successful_requests"],
            rate_limited_requests=row["rate_limited_requests"],
            failed_requests=row["failed_requests"],
            target_rps=row["target_rps"],
            actual_rps=row["actual_rps"],
            average_latency_ms=row["average_latency_ms"],
            duration_seconds=row["duration_seconds"],
            status=SimulationStatus(row["status"]),
        )
