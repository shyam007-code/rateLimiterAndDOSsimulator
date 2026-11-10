# Rate Limiter Lab — Dashboard

A React dashboard that ties the **rate limiter** and **DoS simulator**
backends together into one demo application, with three pages:

1. **Dashboard** — live rate limiter status, metrics, and an
   allowed-vs-rejected requests/sec chart.
2. **Rate Limiter Config** — enable/disable the limiter and edit
   `capacity` / `refill_rate` live.
3. **DoS Simulator** — configure and run a controlled traffic test against
   any authorized local target, with a live progress bar, counters, and a
   success-vs-rate-limited chart streamed over WebSocket.

This frontend talks **directly** to the two FastAPI backends over HTTP/WS
from the browser — there is no third "gateway" server. It doesn't replace
either backend; it's a UI in front of both.

```text
                 ┌────────────────────────┐
                 │     React Dashboard     │  (this project, :5173)
                 │ Dashboard / Config / Sim │
                 └───────────┬─────────────┘
                   REST          REST + WS
                     │               │
                     ▼               ▼
         ┌───────────────────┐  ┌─────────────────────┐
         │  Rate Limiter API │  │  DoS Simulator API   │
         │  (:8000)          │  │  (:8100)             │
         │  Token Bucket     │  │  No rate-limiting    │
         │  Middleware       │  │  logic of its own —  │
         │                   │◄─┤  just sends traffic  │
         └───────────────────┘  └─────────────────────┘
```

## 1. Run all three pieces

You need three terminals (or background processes). Each project is
independent — commands below assume the three folders
(`rate-limiter/`, `dos-simulator/`, `dashboard/`) sit next to each other.

**Terminal 1 — Rate limiter (the protected test app), port 8000:**
```bash
cd rate-limiter
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — DoS simulator (the traffic generator), port 8100:**
```bash
cd dos-simulator
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8100
```

**Terminal 3 — Dashboard, port 5173:**
```bash
cd dashboard
npm install
cp .env.example .env   # defaults already match the ports above
npm run dev
```

Open **http://localhost:5173**.

Both backends already ship with CORS enabled (`CORS_ORIGINS` env var,
default `*`) specifically so this browser app can call them — that was the
only change made to either project to support this dashboard.

## 2. Demonstration script

1. **Dashboard page** — confirm it shows `Rate limiter enabled`, capacity
   100, refill rate 50/s, all counters at 0.
2. **DoS Simulator page** — the form is pre-filled to request 300 requests
   at **150 req/s** (deliberately above the limiter's 50/s refill rate) with
   concurrency 20 against `http://localhost:8000/data`. Click **Start
   Simulation**. Watch the live counters and chart: you'll see successful
   requests plateau and rate-limited (429) requests climb once the token
   bucket empties — a real demonstration of the limiter under load, not
   canned numbers.
3. Switch back to **Dashboard** — the allowed/rejected-per-second chart and
   metrics cards reflect the exact same traffic, confirming both services
   agree on what happened.
4. **Rate Limiter Config page** — raise `Refill Rate` to, say, `200` and
   save. Go back to the simulator and run the same test again: this time
   almost everything succeeds, because the bucket can now refill faster than
   the simulator sends requests. This is the clearest way to show the limiter
   actually doing its job and being tunable live.
5. Try **Disable rate limiter**, re-run the simulation: every request
   succeeds (0 rejected), proving the limiter — not the target app — is what
   was rejecting traffic.
6. Click **Stop** mid-run on a larger simulation (e.g. 100,000 requests) to
   show graceful shutdown.

## 3. Integrating with your own application instead of the demo app

The rate limiter ships two demo endpoints (`/health`, `/data`, `/products`)
just so this dashboard has something to point the simulator at out of the
box. To protect **your own** app instead:

- **If your app is also FastAPI**, import the limiter in-process — see
  `rate-limiter/README.md`'s "Integration" section:
  ```python
  from app.limiter import RateLimiterManager
  from app.middleware import RateLimitMiddleware
  from app.models import RateLimiterConfig

  limiter = RateLimiterManager(RateLimiterConfig(capacity=100, refill_rate=50))
  your_app.state.rate_limiter = limiter
  your_app.add_middleware(RateLimitMiddleware, limiter=limiter)
  ```
  Then point the DoS Simulator's **Target URL** at your app's own port
  instead of the rate limiter's demo port, and the Dashboard/Config pages
  still manage the same `limiter` object if you also mount
  `app.api.rate_limiter.router` on your app.

- **If your app is in another language/framework**, run the rate limiter as
  a standalone reverse proxy in front of it: your app listens on, say,
  `:9000`, and you'd extend the rate limiter's demo endpoints to forward
  allowed requests to `http://localhost:9000` instead of returning a static
  JSON body. Ask if you want this reverse-proxy variant built out — it's a
  small change to `rate-limiter/app/api/demo.py`.

Either way, nothing in this dashboard changes: it only ever talks to the
rate limiter's management API (`/rate-limiter/*`) and the simulator's API —
neither cares what's behind the protected endpoint.

## Project layout

```text
dashboard/
  src/
    lib/
      api.js          fetch/WebSocket clients for both backends
      usePolling.js    simple polling hook used by the Dashboard page
    components/        StatCard, StatusPill, Nav, ConnectionBanner
    pages/
      Dashboard.jsx
      RateLimiterConfig.jsx
      DosSimulator.jsx
    App.jsx            routes + layout
  .env.example          backend URLs (copy to .env)
```

## Configuration

Edit `.env` (copied from `.env.example`):

```bash
VITE_RATE_LIMITER_URL=http://localhost:8000
VITE_SIMULATOR_URL=http://localhost:8100
```

Change these if either backend runs on a different host/port, then restart
`npm run dev`.
