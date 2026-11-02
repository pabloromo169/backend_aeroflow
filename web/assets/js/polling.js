import {
  getFlights,
  getSimulationStatus,
  getSimulations,
  getSummary,
  getTimeline,
} from "./api.js";
import { chooseSimulation } from "./state.js";

export const POLL_INTERVAL_MS = 5000;

export function createPoller({ state, onChange = () => {} }) {
  let timer = null;
  let controller = null;
  let running = false;
  let started = false;
  let cycle = 0;

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function schedule() {
    clearTimer();
    if (!started || document.hidden) return;
    timer = setTimeout(() => {
      void tick();
    }, POLL_INTERVAL_MS);
  }

  async function tick({ force = false } = {}) {
    if (running) {
      if (!force) return;
      controller?.abort(new Error("refresh"));
    }
    const currentCycle = ++cycle;
    running = true;
    clearTimer();
    controller = new AbortController();
    const signal = controller.signal;
    const selectedId = state.selectedId;
    state.lastAttemptAt = new Date();

    const requests = [
      ["simulations", getSimulations({ signal })],
      ["status", getSimulationStatus({ signal })],
    ];
    if (selectedId) {
      requests.push(
        ["summary", getSummary(selectedId, { signal })],
        ["flights", getFlights(selectedId, { page: state.page, signal })],
        ["timeline", getTimeline(selectedId, state.interval, { signal })],
      );
    }

    const results = await Promise.allSettled(requests.map(([, request]) => request));
    if (currentCycle !== cycle) return;

    const aborted = signal.aborted;

    results.forEach((result, index) => {
      const key = requests[index][0];
      if (result.status === "fulfilled") {
        applyResponse(state, key, result.value);
        delete state.errors[key];
        state.lastGood[key] = new Date();
        return;
      }
      const error = result.reason;
      if (aborted || error?.message === "Petición cancelada") {
        return;
      }
      state.errors[key] = error?.message || "No se pudo actualizar este bloque";
    });

    if (!aborted) {
      if (state.simulations.length > 0) {
        const known = state.simulations.some(
          (item) => item.simulation_id === state.selectedId,
        );
        if (!state.selectedId || !known) {
          state.selectedId = chooseSimulation(
            state.simulations,
            state.status,
            state.urlSim,
          );
        }
      }
      state.activeSimulationId = activeId(state.status);
      const essential = ["simulations", "status", "summary", "flights", "timeline"];
      const missing = essential.filter((key) => !state.lastGood[key]);
      const errors = essential.filter((key) => state.errors[key]);
      state.loading =
        Boolean(state.selectedId) && missing.length > 0 && errors.length === 0;
      if (errors.length === 0 && (!state.selectedId || missing.length === 0)) {
        state.lastGoodCycleAt = new Date();
      }
    }

    running = false;
    controller = null;
    onChange(state);
    schedule();
  }

  function start() {
    started = true;
    void tick();
  }

  function stop() {
    started = false;
    cycle += 1;
    running = false;
    clearTimer();
    controller?.abort(new Error("stop"));
    controller = null;
  }

  function refresh() {
    return tick({ force: true });
  }

  function handleVisibility() {
    if (document.hidden) {
      clearTimer();
      return;
    }
    if (started) void tick({ force: true });
  }

  document.addEventListener("visibilitychange", handleVisibility);

  return {
    start,
    stop,
    refresh,
    dispose() {
      stop();
      document.removeEventListener("visibilitychange", handleVisibility);
    },
  };
}

function activeId(status) {
  if (!status) return null;
  return status.state === "running" || status.state === "stopping"
    ? status.simulation_id
    : null;
}

function applyResponse(state, key, body) {
  if (key === "simulations") {
    state.simulations = Array.isArray(body?.items) ? body.items : [];
    return;
  }
  state[key] = body;
}
