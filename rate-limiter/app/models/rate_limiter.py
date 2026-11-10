"""Pydantic models describing rate limiter configuration and metrics."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_ALGORITHMS: tuple[str, ...] = ("token_bucket",)
MAX_CAPACITY: int = 1_000_000
MAX_REFILL_RATE: float = 1_000_000.0


class RateLimiterConfig(BaseModel):
    """Complete, validated rate limiter configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    algorithm: Literal["token_bucket"] = "token_bucket"
    capacity: int = Field(default=100, gt=0, le=MAX_CAPACITY)
    refill_rate: float = Field(
        default=50.0, gt=0, le=MAX_REFILL_RATE, allow_inf_nan=False
    )


class RateLimiterConfigUpdate(BaseModel):
    """Partial configuration update accepted by ``PUT /rate-limiter/config``.

    Omitted (or ``null``) fields keep their current value. The algorithm is
    validated by the manager so that an unsupported value produces a dedicated
    error response instead of a generic validation error.
    """

    model_config = ConfigDict(extra="forbid")

    capacity: int | None = Field(default=None, gt=0, le=MAX_CAPACITY)
    refill_rate: float | None = Field(
        default=None, gt=0, le=MAX_REFILL_RATE, allow_inf_nan=False
    )
    algorithm: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> Self:
        if (
            self.capacity is None
            and self.refill_rate is None
            and self.algorithm is None
        ):
            raise ValueError(
                "at least one of 'capacity', 'refill_rate' or 'algorithm' "
                "must be provided"
            )
        return self


class MetricsResponse(BaseModel):
    """In-memory counters plus the current token level."""

    total_requests: int
    allowed_requests: int
    rejected_requests: int
    current_tokens: float
