"""Unit tests for the asynchronous TokenBucket."""

from __future__ import annotations

import asyncio
import math

import pytest

from app.limiter.token_bucket import TokenBucket
from tests.conftest import FakeClock


@pytest.mark.asyncio
async def test_bucket_starts_full(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=10, refill_rate=1, clock=clock)
    assert await bucket.available_tokens() == 10


@pytest.mark.asyncio
async def test_each_allowed_request_consumes_one_token(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=5, refill_rate=1, clock=clock)
    for _ in range(3):
        decision = await bucket.try_consume()
        assert decision.allowed
        assert decision.retry_after == 0.0
    assert await bucket.available_tokens() == 2


@pytest.mark.asyncio
async def test_rejects_when_empty_and_does_not_consume(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=2, refill_rate=4, clock=clock)
    assert (await bucket.try_consume()).allowed
    assert (await bucket.try_consume()).allowed

    decision = await bucket.try_consume()

    assert not decision.allowed
    assert decision.retry_after == pytest.approx(0.25)
    assert await bucket.available_tokens() == 0


@pytest.mark.asyncio
async def test_refills_over_time(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=10, refill_rate=10, clock=clock)
    for _ in range(10):
        await bucket.try_consume()

    clock.advance(0.5)

    assert await bucket.available_tokens() == pytest.approx(5)


@pytest.mark.asyncio
async def test_tokens_never_exceed_capacity(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=5, refill_rate=100, clock=clock)
    await bucket.try_consume()

    clock.advance(1000)

    assert await bucket.available_tokens() == 5


@pytest.mark.asyncio
async def test_fractional_refill_timing(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=2, refill_rate=2, clock=clock)
    await bucket.try_consume()
    await bucket.try_consume()

    clock.advance(0.25)
    early = await bucket.try_consume()
    assert not early.allowed
    assert early.retry_after == pytest.approx(0.25)
    assert await bucket.available_tokens() == pytest.approx(0.5)

    clock.advance(0.25)
    assert (await bucket.try_consume()).allowed


@pytest.mark.asyncio
async def test_clock_moving_backwards_never_removes_tokens(
    clock: FakeClock,
) -> None:
    bucket = TokenBucket(capacity=5, refill_rate=1, clock=clock)
    await bucket.try_consume()

    clock.advance(-10)

    assert await bucket.available_tokens() == 4


@pytest.mark.asyncio
async def test_reconfigure_clamps_tokens_to_new_capacity(
    clock: FakeClock,
) -> None:
    bucket = TokenBucket(capacity=10, refill_rate=1, clock=clock)

    await bucket.reconfigure(capacity=4, refill_rate=2)

    assert bucket.capacity == 4
    assert bucket.refill_rate == 2
    assert await bucket.available_tokens() == 4


@pytest.mark.asyncio
async def test_reconfigure_settles_elapsed_time_at_old_rate(
    clock: FakeClock,
) -> None:
    bucket = TokenBucket(capacity=10, refill_rate=1, clock=clock)
    for _ in range(10):
        await bucket.try_consume()
    clock.advance(2)

    await bucket.reconfigure(capacity=10, refill_rate=100)
    assert await bucket.available_tokens() == pytest.approx(2)

    clock.advance(0.05)
    assert await bucket.available_tokens() == pytest.approx(7)


@pytest.mark.parametrize(
    ("capacity", "refill_rate"),
    [
        (0, 1),
        (-1, 1),
        (1, 0),
        (1, -1),
        (math.inf, 1),
        (1, math.nan),
    ],
)
def test_invalid_arguments_are_rejected(capacity: float, refill_rate: float) -> None:
    with pytest.raises(ValueError):
        TokenBucket(capacity=capacity, refill_rate=refill_rate)


@pytest.mark.asyncio
async def test_default_clock_is_real_and_monotonic() -> None:
    bucket = TokenBucket(capacity=1, refill_rate=10)
    assert (await bucket.try_consume()).allowed
    assert not (await bucket.try_consume()).allowed

    await asyncio.sleep(0.25)

    assert (await bucket.try_consume()).allowed


@pytest.mark.asyncio
async def test_concurrent_consumption_is_consistent(clock: FakeClock) -> None:
    bucket = TokenBucket(capacity=100, refill_rate=1, clock=clock)

    decisions = await asyncio.gather(*(bucket.try_consume() for _ in range(250)))

    assert sum(d.allowed for d in decisions) == 100
    assert sum(not d.allowed for d in decisions) == 150
    assert await bucket.available_tokens() == 0
