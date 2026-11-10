"""Application factory and ASGI entry point."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.simulations import router as simulations_router
from app.api.websocket import router as websocket_router
from app.config import settings
from app.simulation.manager import SimulationManager
from app.storage import ExperimentRepository
from app.websocket.manager import SimulationHub

logger = logging.getLogger(__name__)

# Origins allowed to call this API from a browser (e.g. the dashboard's dev
# server). Comma-separated via CORS_ORIGINS; "*" (the default) is fine for a
# local demo but should be locked down to real origins in any shared
# deployment. Note: CORSMiddleware does not cover WebSocket connections --
# browsers don't apply the same-origin policy to WS, so no extra
# configuration is needed for the /stream endpoint.
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a sanitized 422 response (no input echo, no internals)."""
    errors = [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the error server-side and return a generic 500 response."""
    logger.error(
        "Unhandled error while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def create_app(
    manager: SimulationManager | None = None,
    hub: SimulationHub | None = None,
) -> FastAPI:
    """Build the application.

    Args:
        manager: Optional pre-built simulation manager (useful for tests, to
            inject a controlled HTTPX transport). A default, SQLite-backed
            manager hitting the real network is created when omitted.
        hub: Optional pre-built WebSocket hub (useful for tests).
    """
    simulation_manager = manager or SimulationManager(
        ExperimentRepository(settings.DATABASE_PATH)
    )
    simulation_hub = hub or SimulationHub(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.simulation_manager.shutdown()

    app = FastAPI(
        title="Controlled HTTP Traffic Simulator",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.simulation_manager = simulation_manager
    app.state.simulation_hub = simulation_hub

    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(simulations_router)
    app.include_router(websocket_router)
    return app


app = create_app()
