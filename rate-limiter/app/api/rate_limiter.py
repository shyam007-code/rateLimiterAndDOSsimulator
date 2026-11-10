"""Management API for the rate limiter."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.limiter.manager import RateLimiterConfigError, RateLimiterManager
from app.models.rate_limiter import (
    MetricsResponse,
    RateLimiterConfig,
    RateLimiterConfigUpdate,
)

router = APIRouter(prefix="/rate-limiter", tags=["rate-limiter"])


def get_manager(request: Request) -> RateLimiterManager:
    """Dependency returning the manager stored on ``app.state.rate_limiter``."""
    manager: RateLimiterManager = request.app.state.rate_limiter
    return manager


ManagerDep = Annotated[RateLimiterManager, Depends(get_manager)]


@router.get("/status", response_model=RateLimiterConfig)
async def get_status(manager: ManagerDep) -> RateLimiterConfig:
    """Return the current configuration."""
    return manager.config


@router.post("/enable", response_model=RateLimiterConfig)
async def enable(manager: ManagerDep) -> RateLimiterConfig:
    """Enable the rate limiter."""
    return manager.enable()


@router.post("/disable", response_model=RateLimiterConfig)
async def disable(manager: ManagerDep) -> RateLimiterConfig:
    """Disable the rate limiter; no request is rejected while disabled."""
    return manager.disable()


@router.put("/config", response_model=RateLimiterConfig)
async def update_config(
    update: RateLimiterConfigUpdate, manager: ManagerDep
) -> RateLimiterConfig:
    """Update capacity, refill rate and/or algorithm."""
    try:
        return await manager.update_config(update)
    except RateLimiterConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(manager: ManagerDep) -> MetricsResponse:
    """Return request counters and the current token level."""
    return await manager.metrics()
