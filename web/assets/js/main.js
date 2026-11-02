import { startSimulation, stopSimulation } from "./api.js";
import { createPoller } from "./polling.js";
import { announce, renderShell } from "./render.js";
import { createConfigPanel } from "./config-panel.js";
import { createConfigForm } from "./config-form.js";
import { createChart } from "./charts.js";
import { initDialogs } from "./dialogs.js";
import { createGatePier, createMetrics } from "./metrics.js";
import { createTable } from "./table.js";
import {
  chooseSimulation,
  createState,
  parseUrl,
  selectSimulation,
  selectedSimulation,
  writeUrl,
} from "./state.js";

const refs = {
  state: null,
  simulationSelect: document.querySelector("#simulation-select"),
  statusPill: document.querySelector("#status-pill"),
  lastUpdate: document.querySelector("#last-update"),
  connectionBanner: document.querySelector("#connection-banner"),
  partialBanner: document.querySelector("#partial-banner"),
  liveRegion: document.querySelector("#live-region"),
  refreshButton: document.querySelector("#refresh-button"),
  configButton: document.querySelector("#config-button"),
  runButton: document.querySelector("#run-button"),
  drawer: document.querySelector("#config-drawer"),
  drawerLoading: document.querySelector("#drawer-loading"),
  drawerCurrent: document.querySelector("#drawer-current"),
  drawerError: document.querySelector("#drawer-error"),
  drawerTitle: document.querySelector("#drawer-title"),
  configFacts: document.querySelector("#config-facts"),
  configGates: document.querySelector("#config-gates"),
  configCatalogs: document.querySelector("#config-catalogs"),
  configJson: document.querySelector("#config-json"),
  configCopy: document.querySelector("#config-copy"),
  tabCurrent: document.querySelector("#tab-current"),
  tabNew: document.querySelector("#tab-new"),
  drawerDuplicate: document.querySelector("#drawer-duplicate"),
  drawerSave: document.querySelector("#drawer-save"),
  formNew: document.querySelector("#drawer-new"),
  formError: document.querySelector("#form-error"),
  formName: document.querySelector("#form-name"),
  formStart: document.querySelector("#form-start"),
  formDays: document.querySelector("#form-days"),
  formOperations: document.querySelector("#form-operations"),
  formOperationsHint: document.querySelector("#form-operations-hint"),
  formInterval: document.querySelector("#form-interval"),
  formSeed: document.querySelector("#form-seed"),
  formSeedRandom: document.querySelector("#form-seed-random"),
  formGates: document.querySelector("#form-gates"),
  formAdvanced: document.querySelector("#form-advanced"),
  formProfilesSummary: document.querySelector("#form-profiles-summary"),
  formProfiles: document.querySelector("#form-profiles"),
  formDelayProbability: document.querySelector("#form-delay-probability"),
  formMaxDelay: document.querySelector("#form-max-delay"),
  formReadonly: document.querySelector("#form-readonly"),
  formJson: document.querySelector("#form-json"),
  departuresBody: document.querySelector("#departures-body"),
  departuresTotal: document.querySelector("#departures-total"),
  filterGate: document.querySelector("#filter-gate"),
  filterAirline: document.querySelector("#filter-airline"),
  filterDestination: document.querySelector("#filter-destination"),
  filterOver: document.querySelector("#filter-over"),
  filtersClear: document.querySelector("#filters-clear"),
  pagePrev: document.querySelector("#page-prev"),
  pageNext: document.querySelector("#page-next"),
  pageStatus: document.querySelector("#page-status"),
  blocks: {
    summary: document.querySelector("#metrics"),
    flights: document.querySelector("#departures-body"),
    timeline: document.querySelector("#evolution"),
  },
};

const state = createState();
refs.state = state;

const dialogs = initDialogs({
  onConfigOpen: () => {
    markPanel("config");
    configForm.showTab("current");
  },
  onConfigClose: () => {
    markPanel("monitor");
    configForm.reset();
  },
});

const configPanel = createConfigPanel({
  refs,
  dialogs,
});

const configForm = createConfigForm({
  refs,
  dialogs,
  onCreated: (created) => {
    refs.drawer.dataset.dirty = "false";
    dialogs.closeDrawer({ force: true });
    selectSimulation(state, created.simulation_id);
    writeUrl(state, { push: true });
    announce(`Configuración ${created.simulation_id} creada`, refs);
    void poller.refresh();
  },
});

const metrics = createMetrics({
  container: document.querySelector("#metrics"),
});

let selectedGate = null;

const gatePier = createGatePier({
  container: document.querySelector("#gates"),
  onGateSelect: (gateId) => {
    selectedGate = selectedGate === gateId ? null : gateId;
    table.setGate(selectedGate);
    document
      .querySelector("#departures-title")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (selectedGate) announce(`Tabla filtrada por la puerta ${selectedGate}`, refs);
    else announce("Filtro de puerta eliminado", refs);
    gatePier.render(state, selectedGate);
  },
});

const chart = createChart({
  container: document.querySelector("#evolution"),
  onIntervalChange: (interval) => {
    if (state.interval === interval) return;
    state.interval = interval;
    writeUrl(state, { push: true });
    syncIntervalButtons(interval);
    announce(`Evolución en ${interval === "hour" ? "horas" : "días"}`, refs);
    void poller.refresh();
  },
});

const intervalButtons = [...document.querySelectorAll(".af-segmented__button")];
chart.bindInterval(intervalButtons);
syncIntervalButtons(state.interval);

const table = createTable({
  refs,
  onChange: () => table.render(state),
  onPageChange: (page) => {
    if (page === state.page) return;
    state.page = page;
    writeUrl(state, { push: true });
    announce(`Página ${page} de salidas`, refs);
    void poller.refresh();
  },
  onClearGate: () => {
    selectedGate = null;
    table.setGate(null);
    gatePier.render(state, selectedGate);
  },
});

const poller = createPoller({
  state,
  onChange: (next) => {
    renderShell(next, refs);
    renderActions(next);
    metrics.render(next);
    gatePier.render(next, selectedGate);
    chart.render(next, next.interval);
    table.render(next);
    configPanel.reload();
    configForm.resetIfNeeded();
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
  selectedGate = null;
  table.clearFilters();
  gatePier.render(state, selectedGate);
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

function syncIntervalButtons(interval) {
  for (const button of document.querySelectorAll(".af-segmented__button")) {
    const active = button.dataset.interval === interval;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("sim");
  if (next && next !== state.selectedId) {
    selectedGate = null;
    table.clearFilters();
    gatePier.render(state, selectedGate);
    selectSimulation(state, next);
    void poller.refresh();
    return;
  }
  const page = Number.parseInt(params.get("page") || "1", 10);
  if (Number.isFinite(page) && page > 0 && page !== state.page) {
    state.page = page;
    void poller.refresh();
  }
  const interval = params.get("interval") === "day" ? "day" : "hour";
  if (interval !== state.interval) {
    state.interval = interval;
    syncIntervalButtons(interval);
    void poller.refresh();
  }
  const wantConfig = params.get("panel") === "config";
  if (wantConfig && !dialogs.isDrawerOpen()) {
    state.panel = "config";
    void configPanel.open();
  } else if (!wantConfig && dialogs.isDrawerOpen()) {
    dialogs.closeDrawer({ force: true });
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
