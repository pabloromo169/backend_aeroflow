import { formatTimeSeconds } from "./format.js";
import { activeSimulationId, orderedSimulations, selectedSimulation } from "./state.js";

export function renderShell(state, refs) {
  renderSimulationSelect(state, refs.simulationSelect);
  renderStatus(state, refs);
  renderBanners(state, refs);
  renderBusy(state, refs);
  renderStaleNotes(state);
}

function renderSimulationSelect(state, select) {
  if (!select) return;
  const simulations = orderedSimulations(state.simulations);
  const signature = simulations
    .map((item) => `${item.simulation_id}:${item.name}`)
    .join("|");

  if (select.dataset.signature !== signature) {
    select.replaceChildren();
    if (simulations.length === 0) {
      const option = new Option("No hay configuraciones", "");
      option.disabled = true;
      select.append(option);
    } else {
      for (const item of simulations) {
        select.append(
          new Option(`${item.simulation_id} · ${item.name}`, item.simulation_id),
        );
      }
    }
    select.dataset.signature = signature;
    select.disabled = simulations.length === 0;
  }

  if (state.selectedId && select.value !== state.selectedId) {
    select.value = state.selectedId;
  }
  const item = selectedSimulation(state);
  select.title = item
    ? `${item.simulation_id} · ${item.name} · ${item.stored_departures} salidas almacenadas`
    : "";
}

function renderStatus(state, refs) {
  const pill = refs.statusPill;
  if (!pill) return;

  let status = "live";
  let label = "En directo";
  if (state.loading) {
    status = "loading";
    label = "Cargando";
  } else if (isOffline(state)) {
    status = "offline";
    label = "Sin conexión";
  } else if (state.summary?.partial) {
    status = "partial";
    label = "Parcial";
  }

  pill.dataset.state = status;
  pill.textContent = label;

  const update = refs.lastUpdate;
  if (update) {
    const stamp = state.lastGoodCycleAt;
    update.textContent = stamp
      ? `Última actualización: ${formatTimeSeconds(stamp)}`
      : "Última actualización: —";
  }
}

function renderBanners(state, refs) {
  const connection = refs.connectionBanner;
  if (connection) {
    const offline = isOffline(state);
    connection.hidden = !offline;
    if (offline) {
      const text = connection.querySelector(".af-banner__text");
      if (text) {
        const lastGood = state.lastGoodCycleAt
          ? ` Último dato correcto: ${formatTimeSeconds(state.lastGoodCycleAt)}.`
          : "";
        text.textContent = `Sin conexión con la API. Se muestran los últimos datos disponibles.${lastGood}`;
      }
    }
  }

  const partial = refs.partialBanner;
  if (partial) {
    const active = activeSimulationId(state.status);
    const viewingActive = active && active === state.selectedId;
    const partialData = Boolean(state.summary?.partial);
    partial.hidden = !partialData && !active;
    if (!partial.hidden) {
      const text = partial.querySelector(".af-banner__text");
      if (text) {
        if (partialData) {
          const status = state.status;
          const progress =
            status && status.simulation_id === state.selectedId
              ? ` ${status.published}/${status.total} publicados.`
              : "";
          text.textContent = `Resultados parciales: NiFi sigue insertando. Los contadores pueden crecer.${progress}`;
        } else if (active) {
          text.textContent = `${active} en curso. Estás viendo ${state.selectedId}; sus datos no son parciales.`;
        }
      }
    }
  }
}

function renderBusy(state, refs) {
  for (const [key, element] of Object.entries(refs.blocks || {})) {
    if (!element) continue;
    const hasData = Boolean(state[key]);
    const stale = Boolean(state.errors[key]) && hasData;
    element.setAttribute("aria-busy", String(state.loading && !hasData));
    element.classList.toggle("is-stale", stale);
  }
}

export function isOffline(state) {
  if (state.loading) return false;
  const essential = ["simulations", "status", "summary", "flights", "timeline"];
  return essential.some((key) => state.errors[key]);
}

function renderStaleNotes(state) {
  const targets = [
    ["summary", "#metrics", "#metrics-stale"],
    ["flights", "#departures-body", "#table-stale"],
    ["timeline", "#evolution", "#chart-stale"],
  ];
  for (const [key, blockSelector, noteSelector] of targets) {
    const block = document.querySelector(blockSelector);
    if (!block) continue;
    let note = document.querySelector(noteSelector);
    const failed = Boolean(state.errors[key]) && Boolean(state[key]);
    if (failed) {
      if (!note) {
        note = document.createElement("p");
        note.id = noteSelector.slice(1);
        note.className = "af-stale-note";
        note.setAttribute("role", "status");
        const head = block.closest(".af-section")?.querySelector(".af-section__head");
        if (head) head.append(note);
        else block.before(note);
      }
      const last = state.lastGood[key];
      note.textContent = last
        ? `Sin actualizar desde ${formatTimeSeconds(last)}. Se muestra el último dato correcto.`
        : "Sin actualizar. Se muestra el último dato correcto.";
    } else if (note) {
      note.remove();
    }
  }
}

export function announce(message, refs) {
  if (!refs.liveRegion) return;
  refs.liveRegion.textContent = "";
  window.setTimeout(() => {
    refs.liveRegion.textContent = message;
  }, 30);
}
