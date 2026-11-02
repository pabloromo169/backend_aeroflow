import { createConfiguration, getConfiguration } from "./api.js";
import {
  datetimeLocalToUtcIso,
  formatMinutes,
  formatNumber,
  formatPercent,
  utcIsoToDatetimeLocal,
} from "./format.js";
import { announce } from "./render.js";

const TIME_BANDS = ["night", "morning", "afternoon", "evening"];
const BAND_LABELS = {
  night: "Noche",
  morning: "Mañana",
  afternoon: "Tarde",
  evening: "Noche cerrada",
};
const VOLUME_TABLES = [
  ["gate_volume_weights", "Volumen por puerta", "gates", "gate_id"],
  ["destination_volume_weights", "Volumen por destino", "destinations", "destination_id"],
  ["time_band_volume_weights", "Volumen por franja", "timeBands", "band"],
];
const MULTIPLIER_TABLES = [
  ["gate_delay_multipliers", "Retraso por puerta", "gates", "gate_id"],
  ["destination_delay_multipliers", "Retraso por destino", "destinations", "destination_id"],
  ["time_band_delay_multipliers", "Retraso por franja", "timeBands", "band"],
];

export function createConfigForm({ refs, dialogs, onCreated }) {
  let base = null;
  let baseFor = null;
  let dirty = false;
  let busy = false;
  const defaults = {
    gates: [],
    profiles: {},
  };

  refs.tabCurrent?.addEventListener("click", () => showTab("current"));
  refs.tabNew?.addEventListener("click", () => showTab("new"));
  refs.drawerDuplicate?.addEventListener("click", () => void duplicate());
  refs.drawerSave?.addEventListener("click", () => void save());
  refs.configCopy?.addEventListener("click", () => void copyJson());
  refs.formSeedRandom?.addEventListener("click", () => {
    if (!refs.formSeed) return;
    refs.formSeed.value = String(randomSeed());
    markDirty();
    updatePreview();
    announce("Semilla aleatoria generada", refs);
    refs.formSeed.focus();
  });

  refs.formNew?.addEventListener("input", () => {
    markDirty();
    updatePreview();
  });
  refs.formNew?.addEventListener("change", () => {
    markDirty();
    updatePreview();
  });
  refs.formNew?.addEventListener("toggle", (event) => {
    if (event.target === refs.formAdvanced && refs.formAdvanced.open) updatePreview();
  }, true);

  function showTab(tab) {
    const current = tab === "current";
    refs.drawerCurrent.hidden = !current;
    refs.formNew.hidden = current;
    refs.tabCurrent.classList.toggle("is-active", current);
    refs.tabNew.classList.toggle("is-active", !current);
    refs.tabCurrent.setAttribute("aria-selected", String(current));
    refs.tabNew.setAttribute("aria-selected", String(!current));
    refs.drawerSave.hidden = current;
    refs.drawerDuplicate.hidden = !current;
    refs.drawer.dataset.tab = tab;
    if (!current) void ensureBase();
  }

  async function ensureBase() {
    const simulationId = refs.state.selectedId;
    if (!simulationId || baseFor === simulationId) return;
    try {
      await prepare(simulationId);
    } catch (error) {
      dialogs.toast(error.message || "No se pudo cargar la configuración", "error");
    }
  }

  function markDirty() {
    dirty = true;
    refs.drawer.dataset.dirty = "true";
  }
  function clearDirty() {
    dirty = false;
    refs.drawer.dataset.dirty = "false";
  }

  async function prepare(simulationId) {
    const config = await getConfiguration(simulationId);
    base = structuredClone(config);
    baseFor = simulationId;
    fillForm(config);
    clearDirty();
  }

  async function copyJson() {
    const text = refs.configJson?.textContent ?? "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      dialogs.toast("JSON copiado al portapapeles", "success");
    } catch {
      dialogs.toast("No se pudo copiar el JSON; selecciona el texto manualmente", "error");
    }
  }

  async function duplicate() {
    const simulationId = refs.state.selectedId;
    if (!simulationId) return;
    try {
      const config = await getConfiguration(simulationId);
      base = structuredClone(config);
      baseFor = simulationId;
      fillForm({ ...config, name: `Copia de ${config.name}` });
      showTab("new");
      markDirty();
      refs.formName?.focus();
    } catch (error) {
      dialogs.toast(error.message || "No se pudo duplicar la configuración", "error");
    }
  }

  function fillForm(config) {
    refs.formName.value = config.name;
    refs.formStart.value = utcIsoToDatetimeLocal(config.simulation_start);
    refs.formDays.value = config.simulation_days;
    refs.formOperations.value = config.total_operations;
    refs.formInterval.value = config.publish_interval_ms;
    refs.formSeed.value = config.random_seed ?? "";
    refs.formDelayProbability.value = config.generation_profiles.base_delay_probability;
    refs.formMaxDelay.value =
      config.generation_profiles.max_delay_minutes_beyond_threshold;

    defaults.gates = config.gates.map((gate) => ({ ...gate }));
    renderGates(defaults.gates);
    defaults.destinations = config.destinations.map((destination) => ({
      id: destination.destination_id,
      label: `${destination.destination_id} · ${destination.name}`,
    }));
    defaults.timeBands = TIME_BANDS.map((band) => ({ id: band, label: BAND_LABELS[band] }));
    defaults.profiles = structuredClone(config.generation_profiles);
    renderProfiles(config.generation_profiles);
    refs.formReadonly.textContent = [
      `Zona horaria fija: ${config.timezone}`,
      `Tasa de defectos fija: ${formatPercent(config.defect_rate * 100, 0)}`,
      `Destinos fijos: ${config.destinations.map((d) => d.destination_id).join(", ")}`,
      `Compañías y flota: ${config.airlines.length} compañías, ${config.aircraft.length} aviones`,
    ].join("\n");
    updateOperationsHint(config.airlines.length);
    updatePreview();
  }

  function renderGates(gates) {
    refs.formGates.replaceChildren(
      ...gates.map((gate, index) => {
        const row = document.createElement("tr");
        const name = document.createElement("td");
        name.textContent = `${gate.gate_id} · ${gate.name}`;

        const terminalCell = document.createElement("td");
        const terminal = document.createElement("select");
        terminal.className = "af-select";
        terminal.dataset.gateIndex = String(index);
        terminal.setAttribute("aria-label", `Terminal de ${gate.gate_id}`);
        for (let number = 1; number <= 5; number += 1) {
          terminal.append(new Option(`T${number}`, `T${number}`));
        }
        terminal.value = gate.terminal_id;
        terminal.addEventListener("change", () => {
          assignTerminal(index, terminal.value);
          markDirty();
          updatePreview();
        });
        terminalCell.append(terminal);

        const thresholdCell = document.createElement("td");
        const threshold = document.createElement("input");
        threshold.className = "af-input";
        threshold.type = "number";
        threshold.min = "1";
        threshold.step = "1";
        threshold.setAttribute("aria-label", `Umbral de ${gate.gate_id} en minutos`);
        threshold.value = String(gate.delay_threshold_minutes);
        threshold.dataset.gateThreshold = String(index);
        threshold.addEventListener("input", () => {
          gates[index].delay_threshold_minutes = Number(threshold.value);
          markDirty();
          updatePreview();
        });
        thresholdCell.append(threshold);

        row.append(name, terminalCell, thresholdCell);
        return row;
      }),
    );
  }

  function assignTerminal(index, terminalId) {
    const gates = defaults.gates;
    const target = gates.findIndex(
      (gate, position) => position !== index && gate.terminal_id === terminalId,
    );
    if (target >= 0) {
      const previous = gates[index].terminal_id;
      gates[target].terminal_id = previous;
      const select = refs.formGates.querySelector(
        `select[data-gate-index="${target}"]`,
      );
      if (select) select.value = previous;
    }
    gates[index].terminal_id = terminalId;
  }

  function renderProfiles(profiles) {
    const wraps = [];
    for (const [key, title, catalog] of VOLUME_TABLES) {
      wraps.push(profileTable(key, title, catalog, profiles[key] ?? {}, "Peso"));
    }
    for (const [key, title, catalog] of MULTIPLIER_TABLES) {
      wraps.push(profileTable(key, title, catalog, profiles[key] ?? {}, "Multiplicador"));
    }
    refs.formProfiles.replaceChildren(...wraps);
    updateProfilesSummary();
  }
  function profileTable(key, title, catalog, values, unit) {
    const wrapper = document.createElement("div");
    wrapper.className = "af-profile";
    const heading = document.createElement("h4");
    heading.className = "af-profile__title";
    heading.textContent = title;
    const hint = document.createElement("p");
    hint.className = "af-profile__hint";
    hint.textContent =
      unit === "Peso"
        ? "Vacío equivale a 1; debe ser mayor que 0."
        : "Vacío equivale a 1; rango 0–4.";
    const table = document.createElement("table");
    table.className = "af-table af-table--compact af-table--form";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const label of ["Clave", unit]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = label;
      headRow.append(th);
    }
    thead.append(headRow);
    const tbody = document.createElement("tbody");
    const options = catalog === "gates"
      ? defaults.gates.map((gate) => ({ id: gate.gate_id, label: gate.gate_id }))
      : catalog === "destinations"
        ? defaults.destinations
        : defaults.timeBands;

    for (const option of options) {
      const row = document.createElement("tr");
      const nameCell = document.createElement("td");
      nameCell.textContent = option.label;
      const valueCell = document.createElement("td");
      const input = document.createElement("input");
      input.className = "af-input";
      input.type = "number";
      input.step = "0.01";
      input.min = unit === "Peso" ? "0.01" : "0";
      input.max = unit === "Peso" ? "100" : "4";
      input.value = values[option.id] === undefined ? "" : String(values[option.id]);
      input.placeholder = "1";
      input.dataset.profile = key;
      input.dataset.key = option.id;
      input.addEventListener("input", () => {
        const target = defaults.profiles[key] ?? (defaults.profiles[key] = {});
        if (input.value === "") delete target[option.id];
        else target[option.id] = Number(input.value);
        updateProfilesSummary();
        updatePreview();
      });
      valueCell.append(input);
      row.append(nameCell, valueCell);
      tbody.append(row);
    }
    table.append(thead, tbody);
    wrapper.append(heading, hint, table);
    return wrapper;
  }

  function updateProfilesSummary() {
    if (!refs.formProfilesSummary) return;
    const count = (value) => Object.keys(value ?? {}).length;
    const profiles = defaults.profiles ?? {};
    refs.formProfilesSummary.textContent = [
      `Perfiles: ${defaults.gates.length} puertas · ${count(profiles.destination_volume_weights)} destinos con peso propio · ${count(profiles.time_band_volume_weights)} franjas con peso propio.`,
      "Las claves vacías usan el valor neutro 1.",
    ].join(" ");
  }

  function updateOperationsHint(airlines = 10) {
    if (!refs.formOperationsHint) return;
    const minimum = Math.ceil((100 * airlines) / (1 - 0.05));
    refs.formOperationsHint.textContent =
      `Mínimo recomendado para ${airlines} compañías: ${formatNumber(minimum)} operaciones.`;
  }

  function collect() {
    const generation = {
      base_delay_probability: Number(refs.formDelayProbability.value),
      max_delay_minutes_beyond_threshold: Number(refs.formMaxDelay.value),
      gate_volume_weights: {},
      destination_volume_weights: {},
      time_band_volume_weights: {},
      gate_delay_multipliers: {},
      destination_delay_multipliers: {},
      time_band_delay_multipliers: {},
    };
    for (const input of refs.formProfiles.querySelectorAll("input[data-profile]")) {
      if (input.value === "") continue;
      generation[input.dataset.profile][input.dataset.key] = Number(input.value);
    }

    const gates = defaults.gates.map((gate) => ({
      gate_id: gate.gate_id,
      name: gate.name,
      terminal_id: gate.terminal_id,
      delay_threshold_minutes: Number(gate.delay_threshold_minutes),
    }));

    const seedText = refs.formSeed.value.trim();
    return {
      name: refs.formName.value.trim(),
      simulation_start: datetimeLocalToUtcIso(refs.formStart.value),
      simulation_days: Number(refs.formDays.value),
      total_operations: Number(refs.formOperations.value),
      publish_interval_ms: Number(refs.formInterval.value),
      random_seed: seedText === "" ? null : Number(seedText),
      timezone: base.timezone,
      defect_rate: base.defect_rate,
      destinations: base.destinations,
      gates,
      airlines: base.airlines,
      aircraft_models: base.aircraft_models,
      aircraft: base.aircraft,
      generation_profiles: generation,
    };
  }

  function updatePreview() {
    if (!base) return;
    try {
      refs.formJson.textContent = JSON.stringify(collect(), null, 2);
    } catch {
      refs.formJson.textContent = "";
    }
    updateProfilesSummary();
  }

  function clearErrors() {
    for (const element of refs.formNew.querySelectorAll("[data-error-for]")) {
      element.textContent = "";
    }
    refs.formError.hidden = true;
  }

  function reset() {
    base = null;
    baseFor = null;
    dirty = false;
    refs.drawer.dataset.dirty = "false";
    clearErrors();
    showTab("current");
  }

  function resetIfNeeded() {
    const simulationId = refs.state.selectedId;
    if (baseFor && simulationId && baseFor !== simulationId) {
      reset();
    }
  }

  function showError(message, fieldPath = []) {
    refs.formError.hidden = false;
    refs.formError.querySelector(".af-banner__text").textContent = message;
    const key = fieldPath[0];
    if (!key) return;
    const target = refs.formNew.querySelector(`[data-error-for="${key}"]`);
    if (target) target.textContent = message;
  }

  async function save() {
    if (!base || busy) return;
    clearErrors();
    const payload = collect();
    const validation = validate(payload);
    if (validation) {
      showError(validation.message, validation.path);
      return;
    }
    busy = true;
    refs.drawerSave.disabled = true;
    try {
      const created = await createConfiguration(payload);
      busy = false;
      refs.drawerSave.disabled = false;
      clearDirty();
      dialogs.toast(
        `Configuración ${created.simulation_id} guardada. Pulsa Arrancar para ejecutarla.`,
        "success",
      );
      onCreated?.(created);
    } catch (error) {
      busy = false;
      refs.drawerSave.disabled = false;
      const field = error.fieldErrors?.[0];
      showError(field?.message || error.message || "No se pudo guardar", field?.path ?? []);
    }
  }

  return {
    prepare,
    duplicate,
    save,
    showTab,
    collect,
    reset,
    resetIfNeeded,
    isDirty: () => dirty,
    baseFor: () => baseFor,
  };
}

function validate(payload) {
  if (!payload.name) {
    return { message: "El nombre es obligatorio", path: ["name"] };
  }
  if (!payload.simulation_start) {
    return { message: "Indica una fecha de inicio válida", path: ["simulation_start"] };
  }
  if (!Number.isInteger(payload.simulation_days) || payload.simulation_days < 7 || payload.simulation_days > 31) {
    return { message: "La duración debe estar entre 7 y 31 días", path: ["simulation_days"] };
  }
  if (!Number.isInteger(payload.total_operations) || payload.total_operations < 100 || payload.total_operations > 100000) {
    return { message: "Las operaciones deben estar entre 100 y 100000", path: ["total_operations"] };
  }
  if (!Number.isInteger(payload.publish_interval_ms) || payload.publish_interval_ms < 0 || payload.publish_interval_ms > 60000) {
    return { message: "El intervalo debe estar entre 0 y 60000 ms", path: ["publish_interval_ms"] };
  }
  if (payload.random_seed !== null && (!Number.isInteger(payload.random_seed) || payload.random_seed < 0)) {
    return { message: "La semilla debe ser un entero no negativo", path: ["random_seed"] };
  }
  const terminals = new Set(payload.gates.map((gate) => gate.terminal_id));
  if (terminals.size !== 5) {
    return { message: "Cada puerta debe tener un terminal distinto", path: ["gates"] };
  }
  for (const gate of payload.gates) {
    if (!Number.isInteger(gate.delay_threshold_minutes) || gate.delay_threshold_minutes < 1) {
      return {
        message: `El umbral de ${gate.gate_id} debe ser al menos 1 minuto`,
        path: ["gates"],
      };
    }
  }
  const profiles = payload.generation_profiles;
  if (
    !Number.isFinite(profiles.base_delay_probability) ||
    profiles.base_delay_probability < 0 ||
    profiles.base_delay_probability > 1
  ) {
    return {
      message: "La probabilidad de retraso debe estar entre 0 y 1",
      path: ["generation_profiles"],
    };
  }
  if (
    !Number.isInteger(profiles.max_delay_minutes_beyond_threshold) ||
    profiles.max_delay_minutes_beyond_threshold < 1 ||
    profiles.max_delay_minutes_beyond_threshold > 1440
  ) {
    return {
      message: "El retraso máximo debe estar entre 1 y 1440 minutos",
      path: ["generation_profiles"],
    };
  }
  for (const key of [
    "gate_volume_weights",
    "destination_volume_weights",
    "time_band_volume_weights",
  ]) {
    if (Object.values(profiles[key]).some((value) => !(value > 0))) {
      return { message: "Los pesos de volumen deben ser positivos", path: ["generation_profiles"] };
    }
  }
  for (const key of [
    "gate_delay_multipliers",
    "destination_delay_multipliers",
    "time_band_delay_multipliers",
  ]) {
    if (Object.values(profiles[key]).some((value) => value < 0 || value > 4)) {
      return {
        message: "Los multiplicadores deben estar entre 0 y 4",
        path: ["generation_profiles"],
      };
    }
  }
  return null;
}

function randomSeed() {
  if (globalThis.crypto?.getRandomValues) {
    const values = new Uint32Array(2);
    globalThis.crypto.getRandomValues(values);
    return (values[0] * 0x200000) + (values[1] >>> 11);
  }
  return Math.floor(Math.random() * Number.MAX_SAFE_INTEGER);
}
