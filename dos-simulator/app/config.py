"""Server-wide settings and hard safety limits.

Limits can be tuned per deployment with environment variables, but a
configuration that exceeds them is always rejected by the API (422) rather
than silently clamped or allowed through.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass(frozen=True, slots=True)
class Settings:
    """Process-wide configuration for the simulator."""

    MAX_TOTAL_REQUESTS: int = _int_env("SIM_MAX_TOTAL_REQUESTS", 100_000)
    MAX_RPS: float = _float_env("SIM_MAX_RPS", 5_000.0)
    MAX_CONCURRENCY: int = _int_env("SIM_MAX_CONCURRENCY", 500)
    MAX_TIMEOUT_SECONDS: float = _float_env("SIM_MAX_TIMEOUT_SECONDS", 120.0)
    WEBSOCKET_UPDATES_PER_SECOND: float = _float_env("SIM_WS_HZ", 15.0)
    DATABASE_PATH: str = os.getenv("SIM_DATABASE_PATH", "simulations.db")


settings = Settings()
