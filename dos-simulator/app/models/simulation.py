"""Pydantic models and enums describing simulations and their results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings

SUPPORTED_METHODS: tuple[str, ...] = ("GET", "POST")


class SimulationStatus(StrEnum):
    """Lifecycle states of a simulation."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset(
    {SimulationStatus.STOPPED, SimulationStatus.COMPLETED, SimulationStatus.FAILED}
)


class SimulationConfig(BaseModel):
    """Validated configuration for one simulation run against an authorized
    target.

    Every numeric field is bounded by the server's configured safety limits
    (see :mod:`app.config`); a request exceeding them is rejected outright.
    """

    model_config = ConfigDict(extra="forbid")

    target_url: str = Field(
        ..., description="Base URL of the authorized test server, e.g. http://localhost:8001"
    )
    endpoint: str = Field(..., description="Path appended to target_url, e.g. '/data'.")
    method: str = Field(default="GET", description="HTTP method: GET or POST.")
    total_requests: int = Field(..., gt=0, le=settings.MAX_TOTAL_REQUESTS)
    target_rps: float = Field(..., gt=0, le=settings.MAX_RPS)
    concurrency: int = Field(..., gt=0, le=settings.MAX_CONCURRENCY)
    timeout: float = Field(default=5.0, gt=0, le=settings.MAX_TIMEOUT_SECONDS)

    @field_validator("target_url")
    @classmethod
    def _validate_target_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("target_url must be an absolute http:// or https:// URL")
        return value.rstrip("/")

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("endpoint must start with '/'")
        return value

    @field_validator("method")
    @classmethod
    def _validate_method(cls, value: str) -> str:
        upper = value.upper()
        if upper not in SUPPORTED_METHODS:
            supported = ", ".join(SUPPORTED_METHODS)
            raise ValueError(f"Unsupported method {value!r}. Supported: {supported}")
        return upper

    @property
    def full_url(self) -> str:
        """The complete URL requests are sent to."""
        return f"{self.target_url}{self.endpoint}"


class SimulationCreateResponse(BaseModel):
    """Response returned immediately after starting a simulation."""

    simulation_id: str
    status: SimulationStatus


class SimulationStatusResponse(BaseModel):
    """Full point-in-time status of one simulation."""

    simulation_id: str
    status: SimulationStatus
    target_url: str
    endpoint: str
    total_requests: int
    completed_requests: int
    successful_requests: int
    rate_limited_requests: int
    client_errors: int
    server_errors: int
    timeouts: int
    network_errors: int
    other_errors: int
    failed_requests: int
    target_rps: float
    current_rps: float
    average_rps: float
    average_latency_ms: float
    minimum_latency_ms: float
    maximum_latency_ms: float
    elapsed_seconds: float


class SimulationSnapshotMessage(BaseModel):
    """Compact periodic payload broadcast over the WebSocket stream."""

    simulation_id: str
    status: SimulationStatus
    total_requests: int
    completed_requests: int
    successful_requests: int
    rate_limited_requests: int
    failed_requests: int
    current_rps: float
    average_latency_ms: float
    elapsed_seconds: float


class ExperimentSummary(BaseModel):
    """A completed experiment's aggregate summary, as stored in SQLite.

    Only aggregates are kept; individual requests, bodies and credentials are
    never stored.
    """

    simulation_id: str
    created_at: datetime
    target_url: str
    endpoint: str
    total_requests: int
    successful_requests: int
    rate_limited_requests: int
    failed_requests: int
    target_rps: float
    actual_rps: float
    average_latency_ms: float
    duration_seconds: float
    status: SimulationStatus
