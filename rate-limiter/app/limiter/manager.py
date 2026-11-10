"""Runtime manager tying together configuration, bucket and metrics."""

from __future__ import annotations

import asyncio
import time

from app.limiter.token_bucket import Clock, Decision, TokenBucket
from app.metrics.collector import MetricsCollector
from app.models.rate_limiter import (
    SUPPORTED_ALGORITHMS,
    MetricsResponse,
    RateLimiterConfig,
    RateLimiterConfigUpdate,
)


class RateLimiterConfigError(ValueError):
    """Raised when a configuration change is not acceptable."""


class UnsupportedAlgorithmError(RateLimiterConfigError):
    """Raised when an unknown rate-limiting algorithm is requested."""


class RateLimiterManager:
    """Owns the token bucket, the on/off switch, config and metrics.

    The middleware only needs :meth:`check`; the management API uses the
    remaining methods.
    """

    def __init__(
        self,
        config: RateLimiterConfig | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        """Create a manager.

        Args:
            config: Initial configuration; defaults to ``RateLimiterConfig()``.
            clock: Monotonic time source; injectable for tests.
        """
        self._config = (config or RateLimiterConfig()).model_copy()
        self._bucket = TokenBucket(
            capacity=self._config.capacity,
            refill_rate=self._config.refill_rate,
            clock=clock,
        )
        self._metrics = MetricsCollector()
        self._config_lock = asyncio.Lock()

    @property
    def config(self) -> RateLimiterConfig:
        """A copy of the current configuration."""
        return self._config.model_copy()

    def enable(self) -> RateLimiterConfig:
        """Enable limiting. Bucket state is preserved."""
        self._config = self._config.model_copy(update={"enabled": True})
        return self.config

    def disable(self) -> RateLimiterConfig:
        """Disable limiting. While disabled, no request is rejected."""
        self._config = self._config.model_copy(update={"enabled": False})
        return self.config

    async def update_config(
        self, update: RateLimiterConfigUpdate
    ) -> RateLimiterConfig:
        """Apply a partial configuration update.

        Raises:
            UnsupportedAlgorithmError: If the requested algorithm is unknown.
        """
        async with self._config_lock:
            if (
                update.algorithm is not None
                and update.algorithm not in SUPPORTED_ALGORITHMS
            ):
                supported = ", ".join(SUPPORTED_ALGORITHMS)
                raise UnsupportedAlgorithmError(
                    f"Unsupported algorithm {update.algorithm!r}. "
                    f"Supported algorithms: {supported}"
                )
            capacity = (
                update.capacity
                if update.capacity is not None
                else self._config.capacity
            )
            refill_rate = (
                update.refill_rate
                if update.refill_rate is not None
                else self._config.refill_rate
            )
            try:
                await self._bucket.reconfigure(capacity, refill_rate)
            except ValueError as exc:
                raise RateLimiterConfigError(str(exc)) from exc
            # No await between reading and writing, so a concurrent
            # enable()/disable() cannot be overwritten.
            self._config = self._config.model_copy(
                update={"capacity": capacity, "refill_rate": refill_rate}
            )
            return self.config

    async def check(self) -> Decision:
        """Decide whether the next request may proceed.

        When disabled, the request is always allowed and no token is consumed.
        Every checked request is counted in the metrics.
        """
        if not self._config.enabled:
            await self._metrics.record(allowed=True)
            return Decision(allowed=True)
        decision = await self._bucket.try_consume()
        await self._metrics.record(allowed=decision.allowed)
        return decision

    async def metrics(self) -> MetricsResponse:
        """Return counters and the current token level."""
        snapshot = await self._metrics.snapshot()
        tokens = await self._bucket.available_tokens()
        return MetricsResponse(
            total_requests=snapshot.total_requests,
            allowed_requests=snapshot.allowed_requests,
            rejected_requests=snapshot.rejected_requests,
            current_tokens=round(tokens, 6),
        )
