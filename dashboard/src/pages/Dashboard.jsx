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
import { rateLimiterApi, RATE_LIMITER_URL } from "../lib/api";
import { usePolling } from "../lib/usePolling";
import StatCard from "../components/StatCard";
import StatusPill from "../components/StatusPill";
import ConnectionBanner from "../components/ConnectionBanner";

const MAX_POINTS = 60;
const POLL_MS = 1000;

export default function Dashboard() {
  const { data: status, error: statusError } = usePolling(
    () => rateLimiterApi.status(),
    POLL_MS,
  );
  const { data: metrics, error: metricsError } = usePolling(
    () => rateLimiterApi.metrics(),
    POLL_MS,
  );

  const [history, setHistory] = useState([]);
  const lastMetrics = useRef(null);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    if (!metrics) return;
    const prev = lastMetrics.current;
    lastMetrics.current = metrics;
    const elapsed = ((Date.now() - startedAt.current) / 1000).toFixed(0);
    const allowedDelta = prev ? metrics.allowed_requests - prev.allowed_requests : 0;
    const rejectedDelta = prev
      ? metrics.rejected_requests - prev.rejected_requests
      : 0;
    setHistory((h) => {
      const next = [
        ...h,
        {
          t: `${elapsed}s`,
          allowed: Math.max(allowedDelta, 0),
          rejected: Math.max(rejectedDelta, 0),
        },
      ];
      return next.length > MAX_POINTS ? next.slice(next.length - MAX_POINTS) : next;
    });
  }, [metrics]);

  const error = statusError || metricsError;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Rate Limiter Dashboard</h1>
          <p className="text-sm text-[var(--text-dim)]">
            Live status from {RATE_LIMITER_URL}
          </p>
        </div>
        {status && (
          <StatusPill
            ok={status.enabled}
            trueLabel="Rate limiter enabled"
            falseLabel="Rate limiter disabled"
          />
        )}
      </div>

      <ConnectionBanner
        error={error}
        serviceName="rate limiter"
        url={RATE_LIMITER_URL}
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total requests"
          value={metrics ? metrics.total_requests.toLocaleString() : "—"}
        />
        <StatCard
          label="Allowed"
          tone="good"
          value={metrics ? metrics.allowed_requests.toLocaleString() : "—"}
        />
        <StatCard
          label="Rejected (429)"
          tone="bad"
          value={metrics ? metrics.rejected_requests.toLocaleString() : "—"}
        />
        <StatCard
          label="Current tokens"
          value={metrics ? metrics.current_tokens.toFixed(2) : "—"}
          sub={status ? `of ${status.capacity} capacity` : undefined}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Algorithm" value={status?.algorithm ?? "—"} />
        <StatCard label="Capacity" value={status?.capacity ?? "—"} />
        <StatCard
          label="Refill rate"
          value={status ? `${status.refill_rate}/s` : "—"}
        />
        <StatCard
          label="Rejection rate"
          tone={
            metrics && metrics.total_requests > 0
              ? metrics.rejected_requests / metrics.total_requests > 0.5
                ? "bad"
                : "warn"
              : "default"
          }
          value={
            metrics && metrics.total_requests > 0
              ? `${((metrics.rejected_requests / metrics.total_requests) * 100).toFixed(1)}%`
              : "0%"
          }
        />
      </div>

      <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
        <h2 className="mb-3 text-sm font-medium text-[var(--text-dim)]">
          Allowed vs. rejected requests / second
        </h2>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="t" stroke="var(--text-dim)" fontSize={12} />
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
                dataKey="allowed"
                stroke="var(--good)"
                dot={false}
                strokeWidth={2}
                name="Allowed/s"
              />
              <Line
                type="monotone"
                dataKey="rejected"
                stroke="var(--bad)"
                dot={false}
                strokeWidth={2}
                name="Rejected/s"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
