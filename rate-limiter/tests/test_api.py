"""HTTPX integration tests for the management API and demo endpoints.

All traffic is in-process (ASGI transport) and bounded; nothing leaves the
test process.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio

from app.limiter.manager import RateLimiterManager
from app.main import create_app
from app.models.rate_limiter import RateLimiterConfig
from tests.conftest import FakeClock, make_client


@pytest.fixture
def manager(clock: FakeClock) -> RateLimiterManager:
    return RateLimiterManager(
        RateLimiterConfig(capacity=5, refill_rate=1), clock=clock
    )


@pytest_asyncio.fixture
async def client(manager: RateLimiterManager) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(create_app(manager)) as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_status_returns_current_config(client: httpx.AsyncClient) -> None:
    response = await client.get("/rate-limiter/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "algorithm": "token_bucket",
        "capacity": 5,
        "refill_rate": 1,
    }


@pytest.mark.asyncio
async def test_disable_then_enable(client: httpx.AsyncClient) -> None:
    disabled = await client.post("/rate-limiter/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert (await client.get("/rate-limiter/status")).json()["enabled"] is False

    enabled = await client.post("/rate-limiter/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert (await client.get("/rate-limiter/status")).json()["enabled"] is True


@pytest.mark.asyncio
async def test_update_config(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/rate-limiter/config", json={"capacity": 100, "refill_rate": 50}
    )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "algorithm": "token_bucket",
        "capacity": 100,
        "refill_rate": 50,
    }
    assert (await client.get("/rate-limiter/status")).json()["capacity"] == 100


@pytest.mark.asyncio
async def test_partial_config_update_keeps_other_values(
    client: httpx.AsyncClient,
) -> None:
    response = await client.put("/rate-limiter/config", json={"capacity": 9})

    assert response.status_code == 200
    assert response.json()["capacity"] == 9
    assert response.json()["refill_rate"] == 1


@pytest.mark.asyncio
async def test_token_bucket_algorithm_is_accepted(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/rate-limiter/config", json={"algorithm": "token_bucket", "capacity": 8}
    )

    assert response.status_code == 200
    assert response.json()["algorithm"] == "token_bucket"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"capacity": 0},
        {"capacity": -1},
        {"refill_rate": 0},
        {"refill_rate": -5},
        {"capacity": "abc"},
        {"capacity": 1.5},
        {"refill_rate": "fast"},
        {"capacity": 10**12},
        {},
        {"unknown_field": 1},
    ],
)
async def test_invalid_config_is_rejected_with_422(
    client: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    response = await client.put("/rate-limiter/config", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert "Traceback" not in response.text
    status = (await client.get("/rate-limiter/status")).json()
    assert status["capacity"] == 5
    assert status["refill_rate"] == 1


@pytest.mark.asyncio
async def test_unsupported_algorithm_returns_400(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/rate-limiter/config", json={"algorithm": "leaky_bucket"}
    )

    assert response.status_code == 400
    assert "Unsupported algorithm" in response.json()["detail"]
    assert "token_bucket" in response.json()["detail"]


@pytest.mark.asyncio
async def test_metrics_start_at_zero(client: httpx.AsyncClient) -> None:
    response = await client.get("/rate-limiter/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "total_requests": 0,
        "allowed_requests": 0,
        "rejected_requests": 0,
        "current_tokens": 5,
    }


@pytest.mark.asyncio
async def test_metrics_reflect_traffic(client: httpx.AsyncClient) -> None:
    statuses = [(await client.get("/health")).status_code for _ in range(7)]

    assert statuses == [200] * 5 + [429] * 2
    metrics = (await client.get("/rate-limiter/metrics")).json()
    assert metrics == {
        "total_requests": 7,
        "allowed_requests": 5,
        "rejected_requests": 2,
        "current_tokens": 0,
    }


@pytest.mark.asyncio
async def test_metrics_report_refilled_tokens(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    for _ in range(5):
        await client.get("/health")

    clock.advance(2)

    assert (await client.get("/rate-limiter/metrics")).json()["current_tokens"] == 2


@pytest.mark.asyncio
async def test_disabled_limiter_lets_all_demo_traffic_through(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/rate-limiter/disable")

    statuses = [(await client.get("/data")).status_code for _ in range(20)]

    assert statuses == [200] * 20
    metrics = (await client.get("/rate-limiter/metrics")).json()
    assert metrics["rejected_requests"] == 0
    assert metrics["current_tokens"] == 5


@pytest.mark.asyncio
async def test_management_api_is_never_rate_limited(
    client: httpx.AsyncClient,
) -> None:
    for _ in range(5):
        await client.get("/health")
    assert (await client.get("/health")).status_code == 429

    assert (await client.get("/rate-limiter/status")).status_code == 200
    assert (await client.get("/rate-limiter/metrics")).status_code == 200
    assert (await client.post("/rate-limiter/disable")).status_code == 200
    assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_rejected_demo_request_has_429_body_and_header(
    client: httpx.AsyncClient,
) -> None:
    for _ in range(5):
        await client.get("/products")

    response = await client.get("/products")

    assert response.status_code == 429
    assert response.json() == {"detail": "Too many requests"}
    assert response.headers["Retry-After"] == "1"


@pytest.mark.asyncio
async def test_demo_endpoints(client: httpx.AsyncClient) -> None:
    health = await client.get("/health")
    data = await client.get("/data")
    products = await client.get("/products")

    assert health.status_code == data.status_code == products.status_code == 200
    assert health.json() == {"status": "ok"}
    assert data.json()["status"] == "ok"
    assert products.json()["status"] == "ok"
    assert len(products.json()["products"]) > 0


@pytest.mark.asyncio
async def test_unhandled_errors_are_sanitized(manager: RateLimiterManager) -> None:
    app = create_app(manager)

    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    app.add_api_route("/boom", boom)

    async with make_client(app, raise_app_exceptions=False) as http_client:
        response = await http_client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_concurrent_http_requests_are_counted_consistently(
    clock: FakeClock,
) -> None:
    manager = RateLimiterManager(
        RateLimiterConfig(capacity=10, refill_rate=1), clock=clock
    )
    async with make_client(create_app(manager)) as http_client:
        responses = await asyncio.gather(
            *(http_client.get("/health") for _ in range(30))
        )
        metrics = (await http_client.get("/rate-limiter/metrics")).json()

    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == 10
    assert statuses.count(429) == 20
    assert metrics["total_requests"] == 30
    assert metrics["allowed_requests"] == 10
    assert metrics["rejected_requests"] == 20
    assert metrics["current_tokens"] == 0
