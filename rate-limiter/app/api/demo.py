"""Demonstration endpoints protected by the rate limiter."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["demo"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@router.get("/data")
async def data() -> dict[str, Any]:
    """Return a small static payload."""
    return {"status": "ok", "data": [1, 2, 3]}


@router.get("/products")
async def products() -> dict[str, Any]:
    """Return a small static product list."""
    return {
        "status": "ok",
        "products": [
            {"id": 1, "name": "Keyboard", "price": 49.99},
            {"id": 2, "name": "Mouse", "price": 19.99},
            {"id": 3, "name": "Monitor", "price": 189.0},
        ],
    }
