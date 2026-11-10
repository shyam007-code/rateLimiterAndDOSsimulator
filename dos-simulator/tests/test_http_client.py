"""Tests for send_request's classification of HTTP outcomes.

All transports here are httpx.MockTransport -- no real socket is ever
opened.
"""

from __future__ import annotations

import httpx
import pytest

from app.http.client import classify_status, send_request


@pytest.mark.asyncio
async def test_successful_response() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "GET", "http://test/data", timeout=1.0)

    assert outcome.category == "successful"
    assert outcome.status_code == 200
    assert outcome.latency_seconds >= 0
    assert outcome.error is None


@pytest.mark.asyncio
async def test_rate_limited_response() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "GET", "http://test/data", timeout=1.0)

    assert outcome.category == "rate_limited"
    assert outcome.status_code == 429


@pytest.mark.asyncio
async def test_client_error_response() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "GET", "http://test/data", timeout=1.0)

    assert outcome.category == "client_error"
    assert outcome.status_code == 404


@pytest.mark.asyncio
async def test_server_error_response() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "GET", "http://test/data", timeout=1.0)

    assert outcome.category == "server_error"
    assert outcome.status_code == 503


@pytest.mark.asyncio
async def test_timeout_is_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "GET", "http://test/data", timeout=1.0)

    assert outcome.category == "timeout"
    assert outcome.status_code is None
    assert outcome.error is not None


@pytest.mark.asyncio
async def test_connection_failure_is_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection refused", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "GET", "http://test/data", timeout=1.0)

    assert outcome.category == "network_error"
    assert outcome.status_code is None


@pytest.mark.asyncio
async def test_post_method_is_sent() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        return httpx.Response(201)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        outcome = await send_request(client, "POST", "http://test/data", timeout=1.0)

    assert seen["method"] == "POST"
    assert outcome.category == "successful"


def test_classify_status_boundaries() -> None:
    assert classify_status(200) == "successful"
    assert classify_status(299) == "successful"
    assert classify_status(429) == "rate_limited"
    assert classify_status(400) == "client_error"
    assert classify_status(404) == "client_error"
    assert classify_status(500) == "server_error"
    assert classify_status(599) == "server_error"
    assert classify_status(600) == "other"
    assert classify_status(101) == "other"
