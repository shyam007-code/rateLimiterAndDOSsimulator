# Rate Limiter Lab

Three independent projects that together demonstrate an HTTP rate limiter
under controlled, authorized load:

```text
rate-limiter/    FastAPI token-bucket rate limiter + management API (:8000)
dos-simulator/   FastAPI controlled traffic simulator (:8100)
dashboard/       React UI tying both together (:5173)
```

**Start here:** [`dashboard/README.md`](dashboard/README.md) has the full
run instructions, a step-by-step demonstration script, and how to point the
simulator at your own application instead of the built-in demo endpoints.

Quick start (three terminals):

```bash
# 1
cd rate-limiter && python3.12 -m venv .venv && source .venv/bin/activate \
  && pip install -r requirements.txt && uvicorn app.main:app --port 8000

# 2
cd dos-simulator && python3.12 -m venv .venv && source .venv/bin/activate \
  && pip install -r requirements.txt && uvicorn app.main:app --port 8100

# 3
cd dashboard && npm install && cp .env.example .env && npm run dev
```

Then open **http://localhost:5173**.

Each project also has its own README with its own install/run/test
instructions and API reference, and can be used standalone without the
other two.
