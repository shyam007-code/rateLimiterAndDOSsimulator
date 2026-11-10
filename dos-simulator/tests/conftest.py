"""Shared test fixtures and helpers.

All tests run fully offline: outbound "network" calls from the simulator are
routed either through an ``httpx.MockTransport`` (synthetic responses) or an
``httpx.ASGITransport`` pointed at a tiny in-process FastAPI app (this
module's ``make_target_app``). No test ever opens a real socket.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse


class FakeClock:
    """Manually advanced clock used in place of ``time.monotonic``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move time forward (or backward, for edge-case tests)."""
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    """A fresh fake clock for each test."""
    return FakeClock()


def make_target_app(rate_limit_after: int | None = None) -> FastAPI:
    """A tiny in-process "authorized test server" used via ASGITransport.

    Returns 200 for every request, or -- if ``rate_limit_after`` is set --
    200 for the first ``rate_limit_after`` requests and 429 after that,
    mimicking a target protected by a rate limiter.
    """
    app = FastAPI()
    state = {"count": 0}

    @app.get("/data")
    @app.post("/data")
    async def data() -> JSONResponse:
        state["count"] += 1
        if rate_limit_after is not None and state["count"] > rate_limit_after:
            return JSONResponse({"detail": "Too many requests"}, status_code=429)
        return JSONResponse({"status": "ok"})

    return app
