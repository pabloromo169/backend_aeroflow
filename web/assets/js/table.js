import {
  formatDateTime,
  formatMinutes,
  formatNumber,
} from "./format.js";

export const PAGE_SIZE = 20;

export function createTable({ refs, onChange, onPageChange, onClearGate }) {
  const filters = {
    gate: "",
    airline: "",
    destination: "",
    over: false,
  };
  let lastSignature = null;
  let lastPage = 1;

  const gateChip = document.querySelector("#gate-filter-chip");
  const gateChipLabel = document.querySelector("#gate-filter-label");

  refs.filterGate?.addEventListener("change", (event) => {
    filters.gate = event.target.value;
    onChange?.();
  });
  refs.filterAirline?.addEventListener("change", (event) => {
    filters.airline = event.target.value;
    onChange?.();
  });
  refs.filterDestination?.addEventListener("change", (event) => {
    filters.destination = event.target.value;
    onChange?.();
  });
  refs.filterOver?.addEventListener("change", (event) => {
    filters.over = event.target.checked;
    onChange?.();
  });
  refs.filtersClear?.addEventListener("click", () => {
    clearFilters();
    onChange?.();
  });
  gateChip?.querySelector("#gate-filter-clear")?.addEventListener("click", () => {
    onClearGate?.();
  });
  refs.pagePrev?.addEventListener("click", () => {
    if (lastPage > 1) onPageChange?.(lastPage - 1);
  });
  refs.pageNext?.addEventListener("click", () => {
    const totalPages = pageCount(refs.state.flights?.total ?? 0);
    if (lastPage < totalPages) onPageChange?.(lastPage + 1);
  });

  function setGate(gateId) {
    filters.gate = gateId ?? "";
    syncFilterControls();
    onChange?.();
  }

  function clearFilters() {
    filters.gate = "";
    filters.airline = "";
    filters.destination = "";
    filters.over = false;
    syncFilterControls();
  }

  function syncFilterControls() {
    if (refs.filterGate) refs.filterGate.value = filters.gate;
    if (refs.filterAirline) refs.filterAirline.value = filters.airline;
    if (refs.filterDestination) refs.filterDestination.value = filters.destination;
    if (refs.filterOver) refs.filterOver.checked = filters.over;
  }

  function render(state) {
    const payload = state.flights ?? { items: [], total: 0, limit: PAGE_SIZE, offset: 0 };
    const items = Array.isArray(payload.items) ? payload.items : [];
    const total = Number(payload.total ?? 0);
    const totalPages = pageCount(total);
    lastPage = state.page;

    if (total > 0 && state.page > totalPages) {
      onPageChange?.(totalPages);
      return;
    }

    const signature = JSON.stringify({
      items,
      total,
      page: state.page,
      filters,
    });

    if (signature === lastSignature) return;
    lastSignature = signature;

    updateOption(refs.filterGate, optionsFor(items, "gate_id"), "Todas", filters.gate);
    updateOption(refs.filterAirline, optionsFor(items, "airline"), "Todas", filters.airline);
    updateOption(
      refs.filterDestination,
      optionsFor(items, "destination_id"),
      "Todos",
      filters.destination,
    );

    const filtered = applyFilters(items, filters);
    const titleTotal = refs.departuresTotal;
    if (titleTotal) {
      titleTotal.textContent = total > 0 ? `(total ${formatNumber(total)})` : "";
    }

    if (gateChip) {
      gateChip.hidden = !filters.gate;
      if (gateChipLabel) gateChipLabel.textContent = `Puerta ${filters.gate}`;
    }

    if (items.length === 0) {
      renderMessage(
        "Sin salidas almacenadas para esta simulación.",
        totalPages,
        state.page,
      );
      return;
    }

    if (filtered.length === 0) {
      renderMessage(
        "Sin filas con estos filtros en esta página.",
        totalPages,
        state.page,
      );
      return;
    }

    refs.departuresBody.replaceChildren(...filtered.map((flight) => row(flight)));
    refs.departuresBody.setAttribute("aria-busy", "false");

    if (refs.pageStatus) refs.pageStatus.textContent = `Página ${state.page} de ${totalPages}`;
    if (refs.pagePrev) refs.pagePrev.disabled = state.page <= 1;
    if (refs.pageNext) refs.pageNext.disabled = state.page >= totalPages;
  }

  function renderMessage(text, totalPages, page) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 9;
    cell.className = "af-empty";
    cell.textContent = text;
    row.append(cell);
    refs.departuresBody.replaceChildren(row);
    refs.departuresBody.setAttribute("aria-busy", "false");
    if (refs.pageStatus) {
      refs.pageStatus.textContent =
        totalPages > 0 ? `Página ${Math.min(page, totalPages)} de ${totalPages}` : "Sin páginas";
    }
    if (refs.pagePrev) refs.pagePrev.disabled = page <= 1;
    if (refs.pageNext) refs.pageNext.disabled = totalPages === 0 || page >= totalPages;
  }

  function reset() {
    lastSignature = null;
  }

  return { render, reset, setGate, clearFilters, filters };
}

function applyFilters(items, filters) {
  return items.filter((flight) => {
    if (filters.gate && flight.gate_id !== filters.gate) return false;
    if (filters.airline && flight.airline !== filters.airline) return false;
    if (filters.destination && flight.destination_id !== filters.destination) return false;
    if (filters.over && !flight.exceeds_threshold) return false;
    return true;
  });
}

function optionsFor(items, key) {
  return [...new Set(items.map((item) => item[key]).filter(Boolean))].sort();
}

function updateOption(select, values, allLabel, selected) {
  if (!select) return;
  const signature = `${values.join("|")}|${selected}`;
  if (select.dataset.signature === signature) return;
  const previous = selected ?? "";
  const options = previous && !values.includes(previous)
    ? [...values, previous].sort()
    : values;
  select.replaceChildren(new Option(allLabel, ""));
  for (const value of options) select.append(new Option(value, value));
  select.value = previous;
  select.dataset.signature = signature;
}

function row(flight) {
  const tr = document.createElement("tr");
  if (flight.exceeds_threshold) tr.classList.add("is-over");

  const flightNumber = cell(flight.flight_number || "—");
  flightNumber.className = "af-table__strong";

  tr.append(
    flightNumber,
    cell(flight.airline || "—"),
    cell(flight.destination_id || "—"),
    cell([flight.gate_id, flight.terminal_id].filter(Boolean).join(" · ") || "—"),
    cell(formatDateTime(flight.scheduled_departure_at)),
    cell(formatDateTime(flight.actual_departure_at)),
    cell(formatMinutes(flight.delay_minutes)),
    cell(formatMinutes(flight.delay_threshold_minutes)),
    statusCell(flight),
  );
  return tr;
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function statusCell(flight) {
  const td = document.createElement("td");
  const badge = document.createElement("span");
  if (flight.exceeds_threshold) {
    badge.className = "af-status af-status--over";
    badge.textContent = "⚠ Supera";
    badge.title = `Retraso ${formatMinutes(flight.delay_minutes)} frente a un umbral de ${formatMinutes(flight.delay_threshold_minutes)}`;
  } else {
    badge.className = "af-status af-status--ok";
    badge.textContent = "Dentro del umbral";
  }
  td.append(badge);
  return td;
}

export function pageCount(total) {
  return Math.max(1, Math.ceil(Number(total || 0) / PAGE_SIZE));
}

export function pageOffset(page) {
  return (page - 1) * PAGE_SIZE;
}
