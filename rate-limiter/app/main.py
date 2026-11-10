"""Application factory and ASGI entry point."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.demo import router as demo_router
from app.api.rate_limiter import router as rate_limiter_router
from app.limiter.manager import RateLimiterManager
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.rate_limiter import RateLimiterConfig

logger = logging.getLogger(__name__)

EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/rate-limiter",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# Origins allowed to call this API from a browser (e.g. the dashboard's dev
# server). Comma-separated via CORS_ORIGINS; "*" (the default) is fine for a
# local demo but should be locked down to real origins in any shared
# deployment.
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
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error"}
    )


def create_app(manager: RateLimiterManager | None = None) -> FastAPI:
    """Build the application.

    Args:
        manager: Optional pre-built manager (useful for tests). A default
            manager is created when omitted.
    """
    limiter = manager or RateLimiterManager(RateLimiterConfig())
    app = FastAPI(title="HTTP Rate Limiter", version="1.0.0")
    app.state.rate_limiter = limiter

    # Starlette runs the LAST-added middleware OUTERMOST, so RateLimitMiddleware
    # is added first (inner) and CORSMiddleware last (outer). That way CORS
    # headers -- including the preflight OPTIONS response -- are added no
    # matter what the rate limiter decides, and a 429 response still carries
    # them so the browser lets the frontend read it instead of reporting a
    # generic CORS failure.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        exempt_path_prefixes=EXEMPT_PATH_PREFIXES,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(rate_limiter_router)
    app.include_router(demo_router)
    return app


app = create_app()
