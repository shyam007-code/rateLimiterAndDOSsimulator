"""Tests for RateLimiterManager: on/off control, config and metrics."""

from __future__ import annotations

import asyncio

import pytest

from app.limiter.manager import RateLimiterManager, UnsupportedAlgorithmError
from app.models.rate_limiter import RateLimiterConfig, RateLimiterConfigUpdate
from tests.conftest import FakeClock


@pytest.fixture
def manager(clock: FakeClock) -> RateLimiterManager:
    return RateLimiterManager(
        RateLimiterConfig(capacity=3, refill_rate=1), clock=clock
    )


@pytest.mark.asyncio
async def test_enabled_state_rejects_excess_requests(
    manager: RateLimiterManager,
) -> None:
    decisions = [await manager.check() for _ in range(4)]

    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[-1].retry_after == pytest.approx(1.0)

    metrics = await manager.metrics()
    assert metrics.total_requests == 4
    assert metrics.allowed_requests == 3
    assert metrics.rejected_requests == 1
    assert metrics.current_tokens == 0


@pytest.mark.asyncio
async def test_disabled_state_never_rejects(manager: RateLimiterManager) -> None:
    manager.disable()

    decisions = [await manager.check() for _ in range(50)]

    assert all(d.allowed for d in decisions)
    metrics = await manager.metrics()
    assert metrics.total_requests == 50
    assert metrics.allowed_requests == 50
    assert metrics.rejected_requests == 0
    assert metrics.current_tokens == 3


@pytest.mark.asyncio
async def test_enable_and_disable_return_updated_config(
    manager: RateLimiterManager,
) -> None:
    assert manager.disable().enabled is False
    assert manager.config.enabled is False
    assert manager.enable().enabled is True
    assert manager.config.enabled is True


@pytest.mark.asyncio
async def test_toggling_preserves_bucket_state(manager: RateLimiterManager) -> None:
    await manager.check()
    await manager.check()

    manager.disable()
    manager.enable()

    assert (await manager.metrics()).current_tokens == 1


@pytest.mark.asyncio
async def test_partial_config_update(manager: RateLimiterManager) -> None:
    config = await manager.update_config(RateLimiterConfigUpdate(refill_rate=5))

    assert config.refill_rate == 5
    assert config.capacity == 3
    assert manager.config.refill_rate == 5


@pytest.mark.asyncio
async def test_lowering_capacity_clamps_tokens(manager: RateLimiterManager) -> None:
    await manager.update_config(RateLimiterConfigUpdate(capacity=2))

    assert (await manager.metrics()).current_tokens == 2


@pytest.mark.asyncio
async def test_raising_capacity_does_not_grant_tokens(
    manager: RateLimiterManager,
) -> None:
    for _ in range(3):
        await manager.check()

    await manager.update_config(RateLimiterConfigUpdate(capacity=10))

    assert (await manager.metrics()).current_tokens == 0


@pytest.mark.asyncio
async def test_config_update_does_not_change_enabled_flag(
    manager: RateLimiterManager,
) -> None:
    manager.disable()

    await manager.update_config(RateLimiterConfigUpdate(capacity=7))

    assert manager.config.enabled is False


@pytest.mark.asyncio
async def test_unsupported_algorithm_is_rejected(
    manager: RateLimiterManager,
) -> None:
    with pytest.raises(UnsupportedAlgorithmError):
        await manager.update_config(
            RateLimiterConfigUpdate(algorithm="leaky_bucket", capacity=50)
        )

    assert manager.config.capacity == 3


@pytest.mark.asyncio
async def test_concurrent_checks_keep_state_consistent(clock: FakeClock) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=50, refill_rate=1), clock=clock
    )

    decisions = await asyncio.gather(*(manager.check() for _ in range(200)))

    metrics = await manager.metrics()
    assert sum(d.allowed for d in decisions) == 50
    assert metrics.total_requests == 200
    assert metrics.allowed_requests == 50
    assert metrics.rejected_requests == 150
    assert metrics.current_tokens == 0


@pytest.mark.asyncio
async def test_concurrent_config_updates_and_checks(clock: FakeClock) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=20, refill_rate=1), clock=clock
    )

    async def toggle() -> None:
        for _ in range(10):
            manager.disable()
            await asyncio.sleep(0)
            manager.enable()
            await asyncio.sleep(0)

    await asyncio.gather(
        toggle(),
        *(manager.update_config(RateLimiterConfigUpdate(refill_rate=2 + i)) for i in range(5)),
        *(manager.check() for _ in range(40)),
    )

    metrics = await manager.metrics()
    assert metrics.total_requests == 40
    assert metrics.allowed_requests + metrics.rejected_requests == 40
    assert 0 <= metrics.current_tokens <= manager.config.capacity
