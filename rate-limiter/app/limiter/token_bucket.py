"""Reusable, framework-agnostic asynchronous token bucket.

This module only knows about rate-limiting state and decisions. It has no
knowledge of HTTP, URLs, users or any particular application.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass

Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of a rate-limit check.

    Attributes:
        allowed: ``True`` if the request may proceed.
        retry_after: Seconds until a token will be available. ``0.0`` when
            the request was allowed.
    """

    allowed: bool
    retry_after: float = 0.0


class TokenBucket:
    """Token bucket with continuous refill and an asyncio lock.

    Tokens are added continuously at ``refill_rate`` tokens per second, never
    exceeding ``capacity``. Each allowed request consumes exactly one token.
    Elapsed time is measured with a monotonic clock.
    """

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        clock: Clock = time.monotonic,
    ) -> None:
        """Create a full bucket.

        Args:
            capacity: Maximum number of tokens (must be positive and finite).
            refill_rate: Tokens added per second (must be positive and finite).
            clock: Monotonic time source in seconds; injectable for tests.

        Raises:
            ValueError: If ``capacity`` or ``refill_rate`` is invalid.
        """
        self._validate(capacity, refill_rate)
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._clock = clock
        self._tokens = self._capacity
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    @staticmethod
    def _validate(capacity: float, refill_rate: float) -> None:
        if not math.isfinite(capacity) or capacity <= 0:
            raise ValueError("capacity must be a positive, finite number")
        if not math.isfinite(refill_rate) or refill_rate <= 0:
            raise ValueError("refill_rate must be a positive, finite number")

    @property
    def capacity(self) -> float:
        """Maximum number of tokens the bucket can hold."""
        return self._capacity

    @property
    def refill_rate(self) -> float:
        """Tokens added per second."""
        return self._refill_rate

    def _refill(self) -> None:
        """Add tokens for the time elapsed. Caller must hold the lock."""
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(
                self._capacity, self._tokens + elapsed * self._refill_rate
            )
            self._last_refill = now

    async def try_consume(self) -> Decision:
        """Consume one token if available.

        Returns:
            An allowed decision, or a rejected decision carrying the number of
            seconds until one full token is available.
        """
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return Decision(allowed=True)
            deficit = 1.0 - self._tokens
            return Decision(allowed=False, retry_after=deficit / self._refill_rate)

    async def available_tokens(self) -> float:
        """Return the current (refilled) token level."""
        async with self._lock:
            self._refill()
            return self._tokens

    async def reconfigure(self, capacity: float, refill_rate: float) -> None:
        """Change capacity and refill rate at runtime.

        Tokens accrued so far are settled at the old rate first. If the new
        capacity is smaller than the current level, the level is clamped; if
        it is larger, no tokens are granted immediately.

        Raises:
            ValueError: If ``capacity`` or ``refill_rate`` is invalid.
        """
        self._validate(capacity, refill_rate)
        async with self._lock:
            self._refill()
            self._capacity = float(capacity)
            self._refill_rate = float(refill_rate)
            self._tokens = min(self._tokens, self._capacity)
