export const PAGE_SIZE = 20;
export const REQUEST_TIMEOUT_MS = 10_000;

export class ApiError extends Error {
  constructor(message, status = 0, body = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.fieldErrors = mapFieldErrors(body);
  }
}

export function mapFieldErrors(body) {
  const detail = body?.detail;
  if (!Array.isArray(detail)) return [];
  return detail.map((item) => ({
    path: Array.isArray(item.loc) ? item.loc.slice(1) : [],
    message: item.msg || "Valor no válido",
  }));
}

export async function fetchJson(path, { signal, timeout = REQUEST_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error("timeout")), timeout);
  const forwardAbort = () => controller.abort(signal.reason);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener("abort", forwardAbort, { once: true });
  }

  try {
    const response = await fetch(`/api${path}`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    const body = await parseBody(response);
    if (!response.ok) {
      throw new ApiError(errorMessage(response, body), response.status, body);
    }
    return body;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted && controller.signal.reason?.message === "timeout") {
      throw new ApiError("La API tardó demasiado en responder");
    }
    if (signal?.aborted) throw new ApiError("Petición cancelada");
    throw new ApiError("No se pudo conectar con la API");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }
}

export async function postJson(path, payload) {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(errorMessage(response, body), response.status, body);
  }
  return body;
}

async function parseBody(response) {
  const type = response.headers.get("content-type") || "";
  if (!type.includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function errorMessage(response, body) {
  if (body && typeof body.detail === "string") return body.detail;
  return `La API respondió ${response.status}`;
}

export function getSimulations(options) {
  return fetchJson("/simulations?limit=100&offset=0", options);
}

export function getSimulationStatus(options) {
  return fetchJson("/simulations/status", options);
}

export function getSummary(simulationId, options) {
  return fetchJson(`/simulations/${encodeURIComponent(simulationId)}/summary`, options);
}

export function getFlights(simulationId, { page = 1, limit = PAGE_SIZE, signal } = {}) {
  const offset = (page - 1) * limit;
  return fetchJson(
    `/simulations/${encodeURIComponent(simulationId)}/flights?limit=${limit}&offset=${offset}`,
    { signal },
  );
}

export function getTimeline(simulationId, interval, options) {
  return fetchJson(
    `/simulations/${encodeURIComponent(simulationId)}/timeline?interval=${encodeURIComponent(interval)}`,
    options,
  );
}

export function getConfiguration(simulationId) {
  return fetchJson(`/configurations/${encodeURIComponent(simulationId)}`);
}

export function createConfiguration(payload) {
  return postJson("/configurations", payload);
}

export function startSimulation(simulationId) {
  return postJson(`/simulations/${encodeURIComponent(simulationId)}/start`);
}

export function stopSimulation() {
  return postJson("/simulations/stop");
}
