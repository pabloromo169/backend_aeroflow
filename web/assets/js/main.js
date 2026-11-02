import { startSimulation, stopSimulation } from "./api.js";
import { createPoller } from "./polling.js";
import { announce, renderShell } from "./render.js";
import { createConfigPanel } from "./config-panel.js";
import { initDialogs } from "./dialogs.js";
import {
  chooseSimulation,
  createState,
  parseUrl,
  selectSimulation,
  selectedSimulation,
  writeUrl,
} from "./state.js";

const refs = {
  state: null,  simulationSelect: document.querySelector("#simulation-select"),
  statusPill: document.querySelector("#status-pill"),
  lastUpdate: document.querySelector("#last-update"),
  connectionBanner: document.querySelector("#connection-banner"),
  partialBanner: document.querySelector("#partial-banner"),
  liveRegion: document.querySelector("#live-region"),
  refreshButton: document.querySelector("#refresh-button"),
  configButton: document.querySelector("#config-button"),
  runButton: document.querySelector("#run-button"),
  drawerLoading: document.querySelector("#drawer-loading"),
  drawerCurrent: document.querySelector("#drawer-current"),
  drawerError: document.querySelector("#drawer-error"),
  drawerTitle: document.querySelector("#drawer-title"),
  configFacts: document.querySelector("#config-facts"),
  configGates: document.querySelector("#config-gates"),
  configCatalogs: document.querySelector("#config-catalogs"),
  configJson: document.querySelector("#config-json"),
  blocks: {
    summary: document.querySelector("#metrics"),
    flights: document.querySelector("#departures-body"),
    timeline: document.querySelector("#evolution"),
  },
};

const state = createState();
refs.state = state;

const dialogs = initDialogs({
  onConfigOpen: () => markPanel("config"),
  onConfigClose: () => markPanel("monitor"),
});

const configPanel = createConfigPanel({
  refs,
  dialogs,
  toast: dialogs.toast,
});

const poller = createPoller({
  state,
  onChange: (next) => {
    renderShell(next, refs);
    renderActions(next);
    configPanel.reload();
    document.title = pageTitle(next);
  },
});

refs.simulationSelect?.addEventListener("change", (event) => {
  handleSimulationChange(event.target.value);
});

refs.refreshButton?.addEventListener("click", () => {
  announce("Actualizando datos", refs);
  void poller.refresh();
});

refs.configButton?.addEventListener("click", () => {
  void configPanel.open();
});

refs.runButton?.addEventListener("click", () => {
  void handleRunAction();
});

async function handleRunAction() {
  const status = state.status;
  const running = status?.state === "running" || status?.state === "stopping";
  if (running) {
    const accepted = await dialogs.confirmAction({
      title: "Parar simulación",
      message:
        "Se solicitará una parada ordenada. Los eventos ya confirmados se conservan.",
      acceptLabel: "Parar",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await stopSimulation();
      dialogs.toast("Parada solicitada", "success");
      await poller.refresh();
    } catch (error) {
      dialogs.toast(error.message || "No se pudo parar la simulación", "error");
    }
    return;
  }

  const simulation = selectedSimulation(state);
  if (!simulation) return;
  const accepted = await dialogs.confirmAction({
    title: "Arrancar simulación",
    message: `Se publicará la configuración ${simulation.simulation_id} · ${simulation.name} y comenzará la simulación. Las salidas se irán almacenando en MongoDB.`,
    acceptLabel: "Arrancar",
  });
  if (!accepted) return;
  try {
    await startSimulation(simulation.simulation_id);
    dialogs.toast(`Simulación ${simulation.simulation_id} arrancada`, "success");
    await poller.refresh();
  } catch (error) {
    dialogs.toast(error.message || "No se pudo arrancar la simulación", "error");
  }
}

function renderActions(next) {
  const hasSimulation = Boolean(next.selectedId);
  const status = next.status;
  const running = status?.state === "running" || status?.state === "stopping";
  if (refs.runButton) {
    refs.runButton.disabled = !hasSimulation && !running;
    refs.runButton.textContent = running ? "Parar" : "Arrancar";
    refs.runButton.classList.toggle("af-button--danger", running);
    refs.runButton.classList.toggle("af-button--accent", !running);
    refs.runButton.title = running
      ? `Simulación ${status.simulation_id} en curso`
      : "Arranca la simulación seleccionada";
  }
}

function markPanel(panel) {
  state.panel = panel;
  writeUrl(state, { push: false });
}

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
  const panel = parseUrl().panel;
  state.panel = panel;
  writeUrl(state, { push: false });
  poller.start();
  if (panel === "config") {
    window.setTimeout(() => void configPanel.open(), 0);
  }
})();
