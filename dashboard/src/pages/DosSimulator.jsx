import { useEffect, useRef, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { simulatorApi, SIMULATOR_URL, RATE_LIMITER_URL } from "../lib/api";
import StatCard from "../components/StatCard";
import ConnectionBanner from "../components/ConnectionBanner";

const TERMINAL = new Set(["COMPLETED", "STOPPED", "FAILED"]);
const MAX_POINTS = 120;

// Deliberately set above the rate limiter's default refill_rate (50/s) so a
// first run demonstrates actual 429s without the user having to tune
// anything first.
const defaultConfig = {
  target_url: RATE_LIMITER_URL,
  endpoint: "/data",
  method: "GET",
  total_requests: 300,
  target_rps: 150,
  concurrency: 20,
  timeout: 3,
};

export default function DosSimulator() {
  const [form, setForm] = useState(defaultConfig);
  const [snapshot, setSnapshot] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);
  const [recent, setRecent] = useState([]);
  const wsRef = useRef(null);
  const startedAt = useRef(null);

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  function updateField(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function connectStream(id) {
    const ws = new WebSocket(simulatorApi.streamUrl(id));
    wsRef.current = ws;
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      setSnapshot(msg);
      setHistory((h) => {
        const next = [
          ...h,
          {
            t: msg.elapsed_seconds.toFixed(1),
            successful: msg.successful_requests,
            rate_limited: msg.rate_limited_requests,
            failed: msg.failed_requests,
          },
        ];
        return next.length > MAX_POINTS ? next.slice(next.length - MAX_POINTS) : next;
      });
      if (TERMINAL.has(msg.status)) {
        ws.close();
        loadRecent();
      }
    };
    ws.onerror = () => setError(new Error("WebSocket connection failed."));
  }

  async function loadRecent() {
    try {
      const items = await simulatorApi.history(5);
      setRecent(items);
    } catch {
      // Non-fatal; history panel just stays stale.
    }
  }

  useEffect(() => {
    loadRecent();
  }, []);

  async function handleStart(e) {
    e.preventDefault();
    setError(null);
    setStarting(true);
    setHistory([]);
    setSnapshot(null);
    try {
      const config = {
        target_url: form.target_url,
        endpoint: form.endpoint,
        method: form.method,
        total_requests: Number(form.total_requests),
        target_rps: Number(form.target_rps),
        concurrency: Number(form.concurrency),
        timeout: Number(form.timeout),
      };
      const created = await simulatorApi.start(config);
      startedAt.current = Date.now();
      setSnapshot({
        simulation_id: created.simulation_id,
        status: created.status,
        total_requests: config.total_requests,
        completed_requests: 0,
        successful_requests: 0,
        rate_limited_requests: 0,
        failed_requests: 0,
        current_rps: 0,
        average_latency_ms: 0,
        elapsed_seconds: 0,
      });
      connectStream(created.simulation_id);
    } catch (err) {
      setError(err);
    } finally {
      setStarting(false);
    }
  }

  async function handleStop() {
    if (!snapshot?.simulation_id) return;
    try {
      await simulatorApi.stop(snapshot.simulation_id);
    } catch (err) {
      setError(err);
    }
  }

  const running = snapshot && !TERMINAL.has(snapshot.status);
  const progressPct = snapshot
    ? Math.min(100, (snapshot.completed_requests / snapshot.total_requests) * 100)
    : 0;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">DoS Simulator</h1>
        <p className="text-sm text-[var(--text-dim)]">
          Controlled traffic generator — {SIMULATOR_URL}. Only point this at
          applications you own or are authorized to test.
        </p>
      </div>

      <ConnectionBanner error={error} serviceName="simulator" url={SIMULATOR_URL} />

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <form
          onSubmit={handleStart}
          className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
        >
          <Field label="Target URL">
            <input
              value={form.target_url}
              onChange={(e) => updateField("target_url", e.target.value)}
              className="input"
              placeholder="http://localhost:8000"
            />
          </Field>
          <Field label="Endpoint">
            <input
              value={form.endpoint}
              onChange={(e) => updateField("endpoint", e.target.value)}
              className="input"
              placeholder="/data"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Method">
              <select
                value={form.method}
                onChange={(e) => updateField("method", e.target.value)}
                className="input"
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
              </select>
            </Field>
            <Field label="Timeout (s)">
              <input
                type="number"
                min="1"
                value={form.timeout}
                onChange={(e) => updateField("timeout", e.target.value)}
                className="input"
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Total requests">
              <input
                type="number"
                min="1"
                value={form.total_requests}
                onChange={(e) => updateField("total_requests", e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Target RPS">
              <input
                type="number"
                min="1"
                value={form.target_rps}
                onChange={(e) => updateField("target_rps", e.target.value)}
                className="input"
              />
            </Field>
          </div>
          <Field label="Concurrency">
            <input
              type="number"
              min="1"
              value={form.concurrency}
              onChange={(e) => updateField("concurrency", e.target.value)}
              className="input"
            />
          </Field>

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={starting || running}
              className="flex-1 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {running ? "Running…" : "Start Simulation"}
            </button>
            <button
              type="button"
              onClick={handleStop}
              disabled={!running}
              className="rounded-lg bg-[var(--bad)]/15 px-4 py-2 text-sm font-medium text-[var(--bad)] transition hover:bg-[var(--bad)]/25 disabled:opacity-40"
            >
              Stop
            </button>
          </div>

          {recent.length > 0 && (
            <div className="pt-2">
              <h3 className="mb-2 text-xs uppercase tracking-wide text-[var(--text-dim)]">
                Recent runs
              </h3>
              <ul className="space-y-1 text-xs text-[var(--text-dim)]">
                {recent.map((r) => (
                  <li key={r.simulation_id} className="flex justify-between">
                    <span className="font-mono">{r.simulation_id}</span>
                    <span>
                      {r.successful_requests}✓ / {r.rate_limited_requests}✗ ·{" "}
                      {r.actual_rps.toFixed(0)} rps
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </form>

        <div>
          {snapshot && (
            <>
              <div className="mb-4 h-2 overflow-hidden rounded-full bg-[var(--surface-2)]">
                <div
                  className="h-full rounded-full bg-[var(--accent)] transition-all"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard
                  label="Status"
                  value={snapshot.status}
                  tone={
                    snapshot.status === "COMPLETED"
                      ? "good"
                      : snapshot.status === "FAILED"
                        ? "bad"
                        : "default"
                  }
                />
                <StatCard
                  label="Completed"
                  value={`${snapshot.completed_requests}/${snapshot.total_requests}`}
                />
                <StatCard
                  label="Successful"
                  tone="good"
                  value={snapshot.successful_requests}
                />
                <StatCard
                  label="Rate limited (429)"
                  tone="bad"
                  value={snapshot.rate_limited_requests}
                />
                <StatCard label="Failed" value={snapshot.failed_requests} />
                <StatCard
                  label="Current RPS"
                  value={snapshot.current_rps.toFixed(1)}
                />
                <StatCard
                  label="Avg latency"
                  value={`${snapshot.average_latency_ms.toFixed(1)} ms`}
                />
                <StatCard
                  label="Elapsed"
                  value={`${snapshot.elapsed_seconds.toFixed(1)}s`}
                />
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
                <h2 className="mb-3 text-sm font-medium text-[var(--text-dim)]">
                  Successful vs. rate-limited over time
                </h2>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={history}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="t"
                        stroke="var(--text-dim)"
                        fontSize={12}
                        label={{
                          value: "seconds",
                          position: "insideBottom",
                          offset: -2,
                          fill: "var(--text-dim)",
                        }}
                      />
                      <YAxis stroke="var(--text-dim)" fontSize={12} allowDecimals={false} />
                      <Tooltip
                        contentStyle={{
                          background: "var(--surface-2)",
                          border: "1px solid var(--border)",
                          borderRadius: 8,
                          color: "var(--text)",
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="successful"
                        stroke="var(--good)"
                        dot={false}
                        strokeWidth={2}
                        name="Successful"
                      />
                      <Line
                        type="monotone"
                        dataKey="rate_limited"
                        stroke="var(--bad)"
                        dot={false}
                        strokeWidth={2}
                        name="Rate limited"
                      />
                      <Line
                        type="monotone"
                        dataKey="failed"
                        stroke="var(--warn)"
                        dot={false}
                        strokeWidth={2}
                        name="Failed"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          )}

          {!snapshot && (
            <div className="flex h-72 items-center justify-center rounded-xl border border-dashed border-[var(--border)] text-sm text-[var(--text-dim)]">
              Configure a run and click Start Simulation.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-[var(--text-dim)]">
        {label}
      </span>
      {children}
    </label>
  );
}
