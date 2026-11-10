import { useEffect, useState } from "react";
import { rateLimiterApi, RATE_LIMITER_URL } from "../lib/api";
import StatusPill from "../components/StatusPill";
import ConnectionBanner from "../components/ConnectionBanner";

export default function RateLimiterConfig() {
  const [status, setStatus] = useState(null);
  const [capacity, setCapacity] = useState("");
  const [refillRate, setRefillRate] = useState("");
  const [algorithm, setAlgorithm] = useState("token_bucket");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null); // { kind: 'ok'|'error', text }
  const [loadError, setLoadError] = useState(null);

  async function refresh() {
    try {
      const s = await rateLimiterApi.status();
      setStatus(s);
      setCapacity(String(s.capacity));
      setRefillRate(String(s.refill_rate));
      setAlgorithm(s.algorithm);
      setLoadError(null);
    } catch (err) {
      setLoadError(err);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleToggle() {
    setBusy(true);
    setMessage(null);
    try {
      const next = status.enabled
        ? await rateLimiterApi.disable()
        : await rateLimiterApi.enable();
      setStatus(next);
      setMessage({
        kind: "ok",
        text: `Rate limiter ${next.enabled ? "enabled" : "disabled"}.`,
      });
    } catch (err) {
      setMessage({ kind: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleSave(e) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const next = await rateLimiterApi.updateConfig({
        capacity: Number(capacity),
        refill_rate: Number(refillRate),
        algorithm,
      });
      setStatus(next);
      setMessage({ kind: "ok", text: "Configuration saved." });
    } catch (err) {
      setMessage({ kind: "error", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Rate Limiter Configuration</h1>
          <p className="text-sm text-[var(--text-dim)]">{RATE_LIMITER_URL}</p>
        </div>
        {status && (
          <StatusPill ok={status.enabled} trueLabel="Enabled" falseLabel="Disabled" />
        )}
      </div>

      <ConnectionBanner
        error={loadError}
        serviceName="rate limiter"
        url={RATE_LIMITER_URL}
      />

      {status && (
        <button
          onClick={handleToggle}
          disabled={busy}
          className={`mb-6 rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${
            status.enabled
              ? "bg-[var(--bad)]/15 text-[var(--bad)] hover:bg-[var(--bad)]/25"
              : "bg-[var(--good)]/15 text-[var(--good)] hover:bg-[var(--good)]/25"
          }`}
        >
          {status.enabled ? "Disable rate limiter" : "Enable rate limiter"}
        </button>
      )}

      <form
        onSubmit={handleSave}
        className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
      >
        <div>
          <label className="mb-1 block text-xs uppercase tracking-wide text-[var(--text-dim)]">
            Algorithm
          </label>
          <select
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          >
            <option value="token_bucket">Token Bucket</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs uppercase tracking-wide text-[var(--text-dim)]">
            Capacity (max tokens)
          </label>
          <input
            type="number"
            min="1"
            value={capacity}
            onChange={(e) => setCapacity(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs uppercase tracking-wide text-[var(--text-dim)]">
            Refill rate (tokens / second)
          </label>
          <input
            type="number"
            min="1"
            step="any"
            value={refillRate}
            onChange={(e) => setRefillRate(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
        </div>

        <button
          type="submit"
          disabled={busy || !status}
          className="w-full rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
        >
          Save Configuration
        </button>

        {message && (
          <div
            className={`rounded-lg px-3 py-2 text-sm ${
              message.kind === "ok"
                ? "bg-[var(--good)]/10 text-[var(--good)]"
                : "bg-[var(--bad)]/10 text-[var(--bad)]"
            }`}
          >
            {message.text}
          </div>
        )}
      </form>
    </div>
  );
}
