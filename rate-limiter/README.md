# HTTP Rate Limiter Backend

An in-memory token-bucket rate limiter for FastAPI, packaged as a reusable ASGI
middleware plus a small management API. Intended for authorized, local test
traffic against applications you own.

```text
Traffic simulator -> RateLimitMiddleware -> Token bucket -> ALLOW -> application
                                                         -> REJECT -> HTTP 429
```

## Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

(`python run.py` does the same; `HOST` and `PORT` environment variables are honored.)

## Test

```bash
pytest -v
```

## API summary

| Method | Endpoint                | Purpose                                         |
|--------|-------------------------|-------------------------------------------------|
| GET    | `/health`               | Demo endpoint (rate limited)                    |
| GET    | `/data`                 | Demo endpoint (rate limited)                    |
| GET    | `/products`             | Demo endpoint (rate limited)                    |
| GET    | `/rate-limiter/status`  | Current configuration                           |
| POST   | `/rate-limiter/enable`  | Enable limiting                                 |
| POST   | `/rate-limiter/disable` | Disable limiting (nothing is rejected)          |
| PUT    | `/rate-limiter/config`  | Update `capacity`, `refill_rate`, `algorithm`   |
| GET    | `/rate-limiter/metrics` | Total/allowed/rejected counts and current tokens |

Rejected requests receive `429 Too Many Requests` with
`{"detail": "Too many requests"}` and a `Retry-After` header (whole seconds).
The `/rate-limiter/*`, `/docs`, `/redoc` and `/openapi.json` paths are exempt
from limiting so the limiter can always be inspected and controlled.

Behavior notes:

* While disabled, requests are counted as allowed and no token is consumed.
* Lowering `capacity` clamps the current tokens; raising it does not grant
  tokens immediately.
* Invalid values return `422`; an unsupported `algorithm` returns `400`.
  Unhandled errors return a generic `500` without internals.

## Integration into an existing FastAPI application

```python
from app.api.rate_limiter import router as rate_limiter_router
from app.limiter import RateLimiterManager
from app.middleware import RateLimitMiddleware
from app.models import RateLimiterConfig

limiter = RateLimiterManager(RateLimiterConfig(capacity=100, refill_rate=50))

shop_app.state.rate_limiter = limiter          # needed by the management API
shop_app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    exempt_path_prefixes=("/rate-limiter", "/docs", "/redoc", "/openapi.json"),
)
shop_app.include_router(rate_limiter_router)   # optional: management endpoints
```

The middleware only requires an object with `async def check(self) -> Decision`,
so it can be used without the management API.

The management endpoints are unauthenticated; run the service on localhost or a
private test network only.
