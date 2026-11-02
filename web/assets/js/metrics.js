import { formatMinutes, formatNumber, formatPercent } from "./format.js";

export function createMetrics({ container }) {
  let last = null;

  function render(state) {
    const totals = state.summary?.totals;
    const empty = !totals || totals.valid_departures === 0;
    const cards = [
      {
        label: "Salidas válidas",
        value: empty ? "0" : formatNumber(totals.valid_departures),
        note: "Registros aceptados por NiFi",
        title: "Salidas con record_valid=true almacenadas en MongoDB",
      },
      {
        label: "Superan umbral",
        value: empty ? "0" : formatNumber(totals.above_threshold),
        note: "Retraso mayor que el umbral",
        alert: !empty && totals.above_threshold > 0,
        title: "Salidas cuyo retraso supera estrictamente el umbral de su puerta",
      },
      {
        label: "Porcentaje superior",
        value: empty ? "—" : formatPercent(totals.above_threshold_percentage, 1),
        note: "Sobre el total de salidas válidas",
        alert: !empty && totals.above_threshold > 0,
        title: "Porcentaje de salidas que superan su umbral",
      },
      {
        label: "Aviones distintos",
        value: empty ? "0" : formatNumber(totals.distinct_aircraft),
        note: "Un avión puede operar en varias puertas",
        title: "Aviones distintos en toda la simulación",
      },
    ];

    const signature = JSON.stringify(cards);
    if (signature === last) return;
    last = signature;

    container.replaceChildren(
      ...cards.map((card) => {
        const article = document.createElement("article");
        article.className = "af-metric";
        if (card.alert) article.classList.add("af-metric--alert");
        article.title = card.title;

        const label = document.createElement("p");
        label.className = "af-metric__label";
        label.textContent = card.label;

        const value = document.createElement("p");
        value.className = "af-metric__value";
        value.textContent = card.value;

        const note = document.createElement("p");
        note.className = "af-metric__note";
        note.textContent = card.note;

        article.append(label, value, note);
        return article;
      }),
    );
  }

  function reset() {
    last = null;
  }

  return { render, reset };
}

export function createGatePier({ container, onGateSelect }) {
  let last = null;

  function render(state, activeGate = null) {
    const gates = state.summary?.gates ?? [];
    if (gates.length === 0) {
      if (last === null) {
        last = "empty";
        container.replaceChildren(emptyMessage("Sin puertas configuradas."));
      }
      return;
    }

    const signature = JSON.stringify({
      gates,
      activeGate,
      partial: state.summary?.partial,
    });
    if (signature === last) return;
    last = signature;

    container.replaceChildren(
      ...gates.map((gate) => {
        const empty = gate.valid_departures === 0;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "af-gate";
        if (activeGate === gate.gate_id) button.classList.add("is-filtered");
        button.dataset.gate = gate.gate_id;        button.setAttribute(
          "aria-label",
          `Puerta ${gate.gate_id}, terminal ${gate.terminal_id}, umbral ${gate.delay_threshold_minutes} minutos, ${gate.valid_departures} salidas, ${gate.above_threshold} superaciones, ${empty ? "sin porcentaje" : formatPercent(gate.above_threshold_percentage, 1)}. Filtrar la tabla por esta puerta.`,
        );
        button.setAttribute("aria-pressed", String(activeGate === gate.gate_id));

        const head = document.createElement("div");
        head.className = "af-gate__head";
        const id = document.createElement("h3");
        id.className = "af-gate__id";
        id.textContent = gate.gate_id;
        const terminal = document.createElement("span");
        terminal.className = "af-gate__terminal";
        terminal.textContent = gate.terminal_id;
        head.append(id, terminal);

        const name = document.createElement("p");
        name.className = "af-gate__name";
        name.textContent = gate.name;

        const threshold = document.createElement("p");
        threshold.className = "af-gate__threshold";
        threshold.textContent = `Umbral ${formatMinutes(gate.delay_threshold_minutes)}`;

        const stats = document.createElement("div");
        stats.className = "af-gate__stats";
        stats.append(
          stat("Salidas", empty ? "0" : formatNumber(gate.valid_departures)),
          stat("Superan", empty ? "0" : formatNumber(gate.above_threshold)),
        );

        const bar = document.createElement("div");
        bar.className = "af-gate__bar";
        bar.setAttribute("aria-hidden", "true");
        const fill = document.createElement("span");
        fill.style.width = empty
          ? "0%"
          : `${Math.min(100, Math.max(0, gate.above_threshold_percentage))}%`;
        bar.append(fill);

        const percent = document.createElement("p");
        percent.className = "af-gate__percent";
        percent.textContent = empty
          ? "—"
          : `${formatPercent(gate.above_threshold_percentage, 1)} por encima`;

        button.append(head, name, threshold, stats, bar, percent);
        button.addEventListener("click", () => onGateSelect?.(gate.gate_id));
        return button;
      }),
    );
  }

  function reset() {
    last = null;
  }

  return { render, reset };
}

function stat(label, value) {
  const paragraph = document.createElement("p");
  const caption = document.createElement("span");
  caption.className = "af-gate__stat-label";
  caption.textContent = label;
  const number = document.createElement("span");
  number.textContent = value;
  paragraph.append(caption, number);
  return paragraph;
}

function emptyMessage(text) {
  const paragraph = document.createElement("p");
  paragraph.className = "af-empty";
  paragraph.textContent = text;
  return paragraph;
}
