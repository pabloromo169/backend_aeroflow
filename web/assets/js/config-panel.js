import { getConfiguration } from "./api.js";
import { formatDateTime, formatMinutes, formatNumber, formatPercent } from "./format.js";

export function createConfigPanel({ refs, dialogs }) {
  let requestId = 0;
  let loadedFor = null;
  let loadingFor = null;
  let lastConfig = null;

  async function open() {
    dialogs.openDrawer();
    const simulationId = refs.state.selectedId;
    if (!simulationId) return;
    if (loadedFor === simulationId) return;
    await load(simulationId);
  }
  async function load(simulationId) {
    if (loadingFor === simulationId) return;
    const current = ++requestId;
    loadingFor = simulationId;
    loadedFor = null;
    refs.drawerLoading.hidden = false;
    refs.drawerCurrent.hidden = true;
    refs.drawerError.hidden = true;
    try {
      const config = await getConfiguration(simulationId);
      if (current !== requestId) return;
      render(config, refs, simulationId);
      lastConfig = config;
      loadedFor = simulationId;
    } catch (error) {
      if (current !== requestId) return;
      showError(error.message || "No se pudo cargar la configuración", refs);
    } finally {
      if (current === requestId) {
        refs.drawerLoading.hidden = true;
        loadingFor = null;
      }
    }
  }

  function reload() {
    const simulationId = refs.state.selectedId;
    if (!simulationId || !dialogs.isDrawerOpen()) return;
    if (loadedFor === simulationId || loadingFor === simulationId) return;
    void load(simulationId);
  }

  return { open, reload, load, current: () => lastConfig };
}
function render(config, refs, simulationId) {
  refs.drawerTitle.textContent = `${config.simulation_id} · ${config.name}`;
  refs.drawerCurrent.hidden = false;

  const simulation = refs.state.simulations.find(
    (item) => item.simulation_id === simulationId,
  );
  const totals = refs.state.summary?.totals;
  const facts = [
    ["Identificador", config.simulation_id],
    ["Nombre", config.name],
    ["Zona horaria", config.timezone],
    ["Inicio", formatDateTime(config.simulation_start)],
    ["Duración", `${config.simulation_days} días`],
    ["Operaciones", formatNumber(config.total_operations)],
    ["Intervalo de publicación", `${formatNumber(config.publish_interval_ms)} ms`],
    ["Semilla", formatNumber(config.random_seed)],
    ["Tasa de defectos", formatPercent(config.defect_rate * 100, 0)],
    [
      "Salidas almacenadas",
      formatNumber(simulation?.stored_departures ?? totals?.valid_departures ?? 0),
    ],
    ["Última emisión", formatDateTime(simulation?.last_emitted_at)],
  ];

  refs.configFacts.replaceChildren(
    ...facts.map(([term, value]) => {
      const wrapper = document.createElement("div");
      wrapper.className = "af-facts__row";
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value ?? "—";
      wrapper.append(dt, dd);
      return wrapper;
    }),
  );

  refs.configGates.replaceChildren(
    ...config.gates.map((gate) => {
      const item = document.createElement("li");
      item.className = "af-gate-list__item";
      const heading = document.createElement("span");
      heading.className = "af-gate-list__id";
      heading.textContent = `${gate.gate_id} · ${gate.terminal_id}`;
      const name = document.createElement("span");
      name.className = "af-gate-list__name";
      name.textContent = gate.name;
      const threshold = document.createElement("span");
      threshold.className = "af-gate-list__threshold";
      threshold.textContent = `Umbral ${formatMinutes(gate.delay_threshold_minutes)}`;
      item.append(heading, name, threshold);
      return item;
    }),
  );

  const destinations = config.destinations
    .map((destination) => `${destination.destination_id} (${destination.name})`)
    .join(" · ");
  refs.configCatalogs.textContent = [
    `Destinos fijos: ${destinations}`,
    `Compañías: ${config.airlines.map((airline) => airline.airline).join(", ")}`,
    `Modelos: ${config.aircraft_models.map((model) => model.name).join(", ")}`,
    `Flota: ${config.aircraft.length} aviones`,
  ].join("\n");

  refs.configJson.textContent = JSON.stringify(config, null, 2);
  refs.drawerError.hidden = true;
}

function showError(message, refs) {
  refs.drawerCurrent.hidden = true;
  refs.drawerError.hidden = false;
  refs.drawerError.querySelector(".af-banner__text").textContent = message;
}
