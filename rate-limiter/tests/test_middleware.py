"""Tests for RateLimitMiddleware on a standalone FastAPI application."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.limiter.manager import RateLimiterManager
from app.limiter.token_bucket import Decision
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.rate_limiter import RateLimiterConfig
from tests.conftest import FakeClock, make_client


class StubLimiter:
    """Minimal limiter proving the middleware only needs ``check()``."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        self.calls = 0

    async def check(self) -> Decision:
        self.calls += 1
        return self.decision


def build_app(
    limiter: object, exempt: tuple[str, ...] = ()
) -> tuple[FastAPI, dict[str, int]]:
    """Create an app with one counting endpoint and one exempt endpoint."""
    app = FastAPI()
    calls = {"protected": 0, "free": 0}

    @app.get("/protected")
    async def protected() -> dict[str, str]:
        calls["protected"] += 1
        return {"status": "ok"}

    @app.get("/free/ping")
    async def free() -> dict[str, str]:
        calls["free"] += 1
        return {"status": "ok"}

    app.add_middleware(
        RateLimitMiddleware, limiter=limiter, exempt_path_prefixes=exempt
    )
    return app, calls


@pytest.mark.asyncio
async def test_allowed_request_reaches_endpoint(clock: FakeClock) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=2, refill_rate=1), clock=clock
    )
    app, calls = build_app(manager)

    async with make_client(app) as client:
        response = await client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls["protected"] == 1


@pytest.mark.asyncio
async def test_rejected_request_returns_429_and_skips_endpoint(
    clock: FakeClock,
) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=1, refill_rate=0.5), clock=clock
    )
    app, calls = build_app(manager)

    async with make_client(app) as client:
        first = await client.get("/protected")
        second = await client.get("/protected")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"detail": "Too many requests"}
    assert second.headers["Retry-After"] == "2"
    assert calls["protected"] == 1


@pytest.mark.asyncio
async def test_tokens_refill_between_requests(clock: FakeClock) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=1, refill_rate=1), clock=clock
    )
    app, calls = build_app(manager)

    async with make_client(app) as client:
        assert (await client.get("/protected")).status_code == 200
        assert (await client.get("/protected")).status_code == 429
        clock.advance(1.0)
        assert (await client.get("/protected")).status_code == 200

    assert calls["protected"] == 2


@pytest.mark.asyncio
async def test_disabled_limiter_never_rejects(clock: FakeClock) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(enabled=False, capacity=1, refill_rate=1), clock=clock
    )
    app, calls = build_app(manager)

    async with make_client(app) as client:
        statuses = [(await client.get("/protected")).status_code for _ in range(10)]

    assert statuses == [200] * 10
    assert calls["protected"] == 10


@pytest.mark.asyncio
async def test_exempt_paths_bypass_the_limiter(clock: FakeClock) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=1, refill_rate=0.1), clock=clock
    )
    app, calls = build_app(manager, exempt=("/free",))

    async with make_client(app) as client:
        for _ in range(5):
            assert (await client.get("/free/ping")).status_code == 200
        assert (await client.get("/protected")).status_code == 200

    assert calls["free"] == 5
    assert (await manager.metrics()).total_requests == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retry_after", "expected_header"),
    [(0.2, "1"), (2.0, "2"), (2.1, "3")],
)
async def test_retry_after_is_rounded_up_to_whole_seconds(
    retry_after: float, expected_header: str
) -> None:
    limiter = StubLimiter(Decision(allowed=False, retry_after=retry_after))
    app, calls = build_app(limiter)

    async with make_client(app) as client:
        response = await client.get("/protected")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == expected_header
    assert calls["protected"] == 0


@pytest.mark.asyncio
async def test_works_with_any_object_providing_check() -> None:
    limiter = StubLimiter(Decision(allowed=True))
    app, calls = build_app(limiter)

    async with make_client(app) as client:
        response = await client.get("/protected")

    assert response.status_code == 200
    assert limiter.calls == 1
    assert calls["protected"] == 1
