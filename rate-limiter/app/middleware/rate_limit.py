"""Reusable ASGI rate-limit middleware.

Usage with any FastAPI/Starlette application::

    app.add_middleware(RateLimitMiddleware, limiter=my_limiter)

``my_limiter`` is any object with an ``async check() -> Decision`` method,
for example :class:`app.limiter.manager.RateLimiterManager`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.limiter.token_bucket import Decision


class RateLimitDecider(Protocol):
    """Anything able to decide whether a request may proceed."""

    async def check(self) -> Decision:
        """Return the decision for the next request."""
        ...


class RateLimitMiddleware:
    """Rejects requests with HTTP 429 when the limiter denies them.

    The decision is made before the downstream application runs, so a
    rejected request never reaches the protected endpoint.
    """

    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimitDecider,
        exempt_path_prefixes: Sequence[str] = (),
    ) -> None:
        """Create the middleware.

        Args:
            app: The wrapped ASGI application.
            limiter: Object deciding whether each request is allowed.
            exempt_path_prefixes: Path prefixes that bypass the limiter
                entirely (not checked and not counted).
        """
        self.app = app
        self._limiter = limiter
        self._exempt = tuple(prefix.rstrip("/") for prefix in exempt_path_prefixes)

    def _is_exempt(self, path: str) -> bool:
        return any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in self._exempt
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_exempt(scope["path"]):
            await self.app(scope, receive, send)
            return

        decision = await self._limiter.check()
        if decision.allowed:
            await self.app(scope, receive, send)
            return

        headers: dict[str, str] = {}
        if decision.retry_after > 0 and math.isfinite(decision.retry_after):
            headers["Retry-After"] = str(max(1, math.ceil(decision.retry_after)))
        response = JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers=headers,
        )
        await response(scope, receive, send)
