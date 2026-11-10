"""Sends one request on a shared client and classifies its outcome.

This module knows nothing about simulations, scheduling or metrics -- only
how to make one request and say what happened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    """The classified result of a single simulated request."""

    status_code: int | None
    category: str
    latency_seconds: float
    error: str | None = None


def classify_status(status_code: int) -> str:
    """Map an HTTP status code to a result category."""
    if status_code == 429:
        return "rate_limited"
    if 200 <= status_code < 300:
        return "successful"
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "server_error"
    return "other"


async def send_request(
    client: httpx.AsyncClient, method: str, url: str, timeout: float
) -> RequestOutcome:
    """Send one request on ``client`` and classify the result.

    Never raises: timeouts, connection failures and any other transport
    error are captured and classified rather than propagated, so a single
    failing request cannot abort the simulation.
    """
    start = time.monotonic()
    try:
        response = await client.request(method, url, timeout=timeout)
    except httpx.TimeoutException as exc:
        return RequestOutcome(None, "timeout", time.monotonic() - start, str(exc))
    except httpx.TransportError as exc:
        return RequestOutcome(None, "network_error", time.monotonic() - start, str(exc))
    except httpx.HTTPError as exc:
        return RequestOutcome(None, "other", time.monotonic() - start, str(exc))
    latency = time.monotonic() - start
    return RequestOutcome(
        response.status_code, classify_status(response.status_code), latency, None
    )
