"""Shared test helpers."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI


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


def make_client(
    app: FastAPI, *, raise_app_exceptions: bool = True
) -> httpx.AsyncClient:
    """Create an in-process HTTPX client bound to ``app`` (no network)."""
    transport = httpx.ASGITransport(
        app=app, raise_app_exceptions=raise_app_exceptions
    )
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")
