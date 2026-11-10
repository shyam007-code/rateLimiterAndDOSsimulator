# Controlled HTTP Traffic Simulator

A controlled, local HTTP traffic simulator for an authorized test lab. It
drives paced, concurrency-bounded load at a target you specify, classifies
every response, and streams aggregate metrics over a WebSocket. It is a
separate service from the rate limiter it is meant to exercise — it contains
no token bucket and no rate-limiting logic of its own; it only observes the
target's responses.

```text
Flutter / any client
        |
   REST + WebSocket
        |
        v
 SIMULATOR BACKEND (this project)
        |
     HTTPX (paced, bounded concurrency)
        |
        v
 AUTHORIZED TEST SERVER
   (e.g. the rate limiter project, protecting your app)
        |
   200 / 429 / 4xx / 5xx / timeout / network error
        |
        v
 Simulator metrics -> REST status + WebSocket stream -> SQLite history
```

**Use only against applications and infrastructure you own or are explicitly
authorized to test.** The simulator requires an explicit `target_url`, has no
IP spoofing, evasion, rate-limit bypass, distributed coordination, botnet or
target-discovery functionality, and enforces configurable safety ceilings on
total requests, RPS and concurrency (see below).

## Installation

```bash
cd dos-simulator
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8100
```

(`python run.py` does the same; `HOST` and `PORT` environment variables are
honored. Defaults to port 8100 so it can run alongside a rate limiter on
8000 without clashing.)

## Test

```bash
pytest -v
```

All 79 tests run fully offline: outbound calls are routed through
`httpx.MockTransport` or an in-process `httpx.ASGITransport` target app, so
no test ever opens a real socket or sends traffic anywhere.

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/simulations` | Validate config, start a simulation as a background task, return its id |
| GET | `/simulations/{id}` | Current status, counters and latency stats |
| POST | `/simulations/{id}/stop` | Gracefully stop a running simulation |
| GET | `/simulations/history` | Recent completed experiment summaries (SQLite) |
| GET | `/simulations/history/{id}` | One completed experiment's summary |
| WS | `/simulations/{id}/stream` | Periodic aggregate snapshots (~15/sec), closes on completion |

## Flutter / client integration

**Start a simulation** — `POST /simulations`

```json
{
  "target_url": "http://localhost:8001",
  "endpoint": "/data",
  "method": "GET",
  "total_requests": 1000,
  "target_rps": 100,
  "concurrency": 20,
  "timeout": 5
}
```
→
```json
{ "simulation_id": "abc123", "status": "RUNNING" }
```

**Stream live metrics** — connect to `ws://host:8100/simulations/{id}/stream`.
Messages arrive ~15 times per second (configurable), never once per request:

```json
{
  "simulation_id": "abc123",
  "status": "RUNNING",
  "total_requests": 10000,
  "completed_requests": 4500,
  "successful_requests": 1000,
  "rate_limited_requests": 3500,
  "failed_requests": 0,
  "current_rps": 99.2,
  "average_latency_ms": 22.4,
  "elapsed_seconds": 45.3
}
```

The stream closes automatically right after the final (`COMPLETED` /
`STOPPED` / `FAILED`) snapshot.

**Full status** — `GET /simulations/{id}` returns the same fields plus
`client_errors`, `server_errors`, `timeouts`, `network_errors`,
`other_errors`, `target_rps`, `average_rps`, `minimum_latency_ms` and
`maximum_latency_ms`.

**Stop** — `POST /simulations/{id}/stop` returns the same shape with
`status: "STOPPED"`, or `409` if it already finished, or `404` if the id is
unknown.

## Safety limits

Enforced by `SimulationConfig` validation (422 if exceeded), tunable via
environment variables:

| Limit | Default | Env var |
|---|---|---|
| Max total requests | 100,000 | `SIM_MAX_TOTAL_REQUESTS` |
| Max target RPS | 5,000 | `SIM_MAX_RPS` |
| Max concurrency | 500 | `SIM_MAX_CONCURRENCY` |
| Max per-request timeout | 120s | `SIM_MAX_TIMEOUT_SECONDS` |

A simulation also always stops on its own once `total_requests` completes —
it never runs indefinitely.

## Example controlled test

Against a local target (e.g. the companion rate-limiter project running on
`:8001`):

```bash
curl -X POST http://127.0.0.1:8100/simulations \
  -H 'content-type: application/json' \
  -d '{
    "target_url": "http://localhost:8001",
    "endpoint": "/data",
    "method": "GET",
    "total_requests": 200,
    "target_rps": 20,
    "concurrency": 5,
    "timeout": 2
  }'
```

Then watch it live:

```bash
# using websocat, wscat, or any WebSocket client
wscat -c ws://127.0.0.1:8100/simulations/<simulation_id>/stream
```

Do not point `target_url` at any system you do not own or lack explicit
authorization to test.

## Project layout

```text
app/
  config.py          safety limits (env-tunable)
  models/             Pydantic config, status, snapshot and summary models
  http/client.py       sends one request, classifies the outcome
  metrics/collector.py aggregate counters + latency stats (no per-request log)
  simulation/
    scheduler.py       paces dispatch toward target_rps
    worker.py           claims indices, applies pacing, records outcomes
    engine.py           lifecycle: start/stop/run/status for one simulation
    manager.py          registry of simulations + SQLite persistence on completion
  websocket/manager.py  one broadcaster task per simulation, ~15 updates/sec
  storage.py            SQLite summaries only -- no per-request storage
  api/                 REST + WebSocket routes
tests/                 79 tests: config, scheduler, HTTP client, metrics,
                       engine, REST API, WebSocket -- all offline
```
