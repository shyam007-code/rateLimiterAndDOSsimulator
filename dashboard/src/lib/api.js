// Thin fetch wrappers for the two backend services. Both base URLs are
// configurable via .env (see .env.example) so the dashboard can point at
// whatever host/port each service actually runs on.

export const RATE_LIMITER_URL =
  import.meta.env.VITE_RATE_LIMITER_URL || "http://localhost:8000";
export const SIMULATOR_URL =
  import.meta.env.VITE_SIMULATOR_URL || "http://localhost:8100";

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(baseUrl, path, options = {}) {
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      headers: { "content-type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(
      `Could not reach ${baseUrl}. Is the service running?`,
      0,
      null,
    );
  }
  let body = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? body.detail
        : body;
    const message =
      typeof detail === "string" ? detail : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, detail);
  }
  return body;
}

// ---- Rate limiter API --------------------------------------------------

export const rateLimiterApi = {
  status: () => request(RATE_LIMITER_URL, "/rate-limiter/status"),
  metrics: () => request(RATE_LIMITER_URL, "/rate-limiter/metrics"),
  enable: () =>
    request(RATE_LIMITER_URL, "/rate-limiter/enable", { method: "POST" }),
  disable: () =>
    request(RATE_LIMITER_URL, "/rate-limiter/disable", { method: "POST" }),
  updateConfig: (config) =>
    request(RATE_LIMITER_URL, "/rate-limiter/config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
};

// ---- Simulator API -------------------------------------------------------

export const simulatorApi = {
  start: (config) =>
    request(SIMULATOR_URL, "/simulations", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  status: (id) => request(SIMULATOR_URL, `/simulations/${id}`),
  stop: (id) =>
    request(SIMULATOR_URL, `/simulations/${id}/stop`, { method: "POST" }),
  history: (limit = 20) =>
    request(SIMULATOR_URL, `/simulations/history?limit=${limit}`),
  streamUrl: (id) =>
    `${SIMULATOR_URL.replace(/^http/, "ws")}/simulations/${id}/stream`,
};
