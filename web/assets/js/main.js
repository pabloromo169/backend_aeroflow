import { createPoller } from "./polling.js";
import { announce, renderShell } from "./render.js";
import {
  chooseSimulation,
  createState,
  selectSimulation,
  selectedSimulation,
  writeUrl,
} from "./state.js";

const refs = {
  simulationSelect: document.querySelector("#simulation-select"),
  statusPill: document.querySelector("#status-pill"),
  lastUpdate: document.querySelector("#last-update"),
  connectionBanner: document.querySelector("#connection-banner"),
  partialBanner: document.querySelector("#partial-banner"),
  liveRegion: document.querySelector("#live-region"),
  blocks: {
    summary: document.querySelector("#metrics"),
    flights: document.querySelector("#departures-body"),
    timeline: document.querySelector("#evolution"),
  },
};

const state = createState();

const poller = createPoller({
  state,
  onChange: (next) => {
    renderShell(next, refs);
    document.title = pageTitle(next);
  },
});

refs.simulationSelect?.addEventListener("change", (event) => {
  handleSimulationChange(event.target.value);
});

function handleSimulationChange(simulationId) {
  if (!simulationId || simulationId === state.selectedId) return;
  selectSimulation(state, simulationId);
  writeUrl(state, { push: true });
  announce(`Simulación ${simulationId} seleccionada`, refs);
  void poller.refresh();
}

function pageTitle(next) {
  const item = selectedSimulation(next);
  return item
    ? `${item.simulation_id} · AeroFlow · Centro de control`
    : "AeroFlow · Centro de control";
}

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("sim");
  if (next && next !== state.selectedId) {
    selectSimulation(state, next);
    void poller.refresh();
  }
});

window.addEventListener("beforeunload", () => poller.dispose(), { once: true });

const initial = new URLSearchParams(window.location.search);
if (initial.get("sim")) state.urlSim = initial.get("sim");

void (async () => {
  await poller.refresh();
  if (!state.selectedId && state.simulations.length > 0) {
    state.selectedId = chooseSimulation(state.simulations, state.status, state.urlSim);
  }
  writeUrl(state, { push: false });
  poller.start();
})();
