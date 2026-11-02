export const DEFAULT_INTERVAL = "hour";
export const DEFAULT_PAGE = 1;

export function parseUrl(search = window.location.search) {
  const params = new URLSearchParams(search);
  const rawPage = Number.parseInt(params.get("page") || "1", 10);
  const page = Number.isFinite(rawPage) && rawPage > 0 ? rawPage : DEFAULT_PAGE;
  const interval = params.get("interval") === "day" ? "day" : DEFAULT_INTERVAL;
  const panel = params.get("panel") === "config" ? "config" : "monitor";
  return {
    sim: params.get("sim"),
    page,
    interval,
    panel,
  };
}

export function buildUrl(state, overrides = {}) {
  const params = new URLSearchParams();
  const sim = overrides.sim ?? state.selectedId;
  if (sim) params.set("sim", sim);
  if (state.panel === "config") params.set("panel", "config");
  if (state.page > 1) params.set("page", String(state.page));
  if (state.interval !== DEFAULT_INTERVAL) params.set("interval", state.interval);
  const query = params.toString();
  return query ? `?${query}` : window.location.pathname;
}

export function writeUrl(state, { push = false } = {}) {
  const url = buildUrl(state);
  if (push) window.history.pushState({}, "", url);
  else window.history.replaceState({}, "", url);
}

export function createState(overrides = {}) {
  const fromUrl = parseUrl();
  return {
    simulations: [],
    selectedId: null,
    summary: null,
    flights: null,
    timeline: null,
    status: null,
    page: fromUrl.page,
    interval: fromUrl.interval,
    panel: fromUrl.panel,
    urlSim: fromUrl.sim ?? null,
    loading: true,
    errors: {},
    lastGood: {},
    lastGoodCycleAt: null,
    lastAttemptAt: null,
    activeSimulationId: null,
    ...overrides,
  };
}

export function selectSimulation(state, simulationId, { resetPage = true } = {}) {
  state.selectedId = simulationId;
  state.urlSim = null;
  if (resetPage) state.page = DEFAULT_PAGE;
  state.summary = null;
  state.flights = null;
  state.timeline = null;
  state.errors = {};
  state.lastGood = {};
  state.lastGoodCycleAt = null;
}

export function orderedSimulations(simulations = []) {
  return [...simulations].sort((left, right) => {
    if (left.simulation_id === "SIM-01") return -1;
    if (right.simulation_id === "SIM-01") return 1;
    return left.simulation_id.localeCompare(right.simulation_id);
  });
}

export function chooseSimulation(simulations, status, preferred) {
  const available = new Set(simulations.map((item) => item.simulation_id));
  if (preferred && available.has(preferred)) return preferred;
  const active = activeSimulationId(status);
  if (active && available.has(active)) return active;
  if (available.has("SIM-01")) return "SIM-01";
  return orderedSimulations(simulations)[0]?.simulation_id ?? null;
}

export function activeSimulationId(status) {
  if (!status) return null;
  return status.state === "running" || status.state === "stopping"
    ? status.simulation_id
    : null;
}

export function selectedSimulation(state) {
  return state.simulations.find((item) => item.simulation_id === state.selectedId) ?? null;
}

export function isDataStale(state) {
  return Boolean(
    state.errors.summary || state.errors.flights || state.errors.timeline || state.errors.status,
  );
}
