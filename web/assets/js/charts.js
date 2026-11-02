import { formatDateTime, formatNumber, formatPercent } from "./format.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const CHART_HEIGHT = 240;
const PADDING = { top: 16, right: 12, bottom: 34, left: 44 };

export function createChart({ container, onIntervalChange }) {
  let last = null;
  let activeInterval = "hour";

  function render(state, interval = activeInterval) {
    activeInterval = interval;
    const items = Array.isArray(state.timeline?.items) ? state.timeline.items : [];
    const empty = items.length === 0;
    const signature = JSON.stringify({ items, interval, empty });
    if (signature === last) return;
    last = signature;

    container.querySelector(".af-chart__placeholder")?.remove();
    container.querySelector("svg")?.remove();
    container.querySelector(".af-chart__empty")?.remove();

    const range = document.querySelector("#chart-range");
    if (range) {
      range.textContent =
        items.length > 0
          ? `${formatDateTime(items[0].timestamp)} — ${formatDateTime(items[items.length - 1].timestamp)}`
          : "";
    }

    if (empty) {
      const message = document.createElement("p");
      message.className = "af-chart__empty af-empty";
      message.textContent = "Sin salidas en este intervalo.";
      container.prepend(message);
      return;
    }

    container.prepend(buildChart(items, interval));
  }

  function reset() {
    last = null;
  }

  function bindInterval(buttons) {
    for (const button of buttons) {
      button.addEventListener("click", () => {
        const interval = button.dataset.interval;
        if (!interval || interval === activeInterval) return;
        onIntervalChange?.(interval);
      });
    }
  }

  return { render, reset, bindInterval };
}

function buildChart(items, interval) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 1000 ${CHART_HEIGHT}`);
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    `Evolución de ${items.length} ${interval === "hour" ? "horas" : "días"} con salidas bajo y sobre el umbral.`,
  );
  svg.classList.add("af-chart__svg");

  const plotWidth = 1000 - PADDING.left - PADDING.right;
  const plotHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;
  const max = Math.max(1, ...items.map((item) => item.departures));
  const step = plotWidth / items.length;
  const barWidth = Math.max(3, Math.min(28, step * 0.62));

  for (let index = 0; index <= 4; index += 1) {
    const value = Math.round((max / 4) * index);
    const y = PADDING.top + plotHeight - (value / max) * plotHeight;
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", String(PADDING.left));
    line.setAttribute("x2", String(1000 - PADDING.right));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("class", index === 0 ? "af-chart__axis" : "af-chart__grid");
    svg.append(line);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", String(PADDING.left - 8));
    label.setAttribute("y", String(y + 4));
    label.setAttribute("text-anchor", "end");
    label.setAttribute("class", "af-chart__tick");
    label.textContent = formatNumber(value);
    svg.append(label);
  }

  const labelEvery = Math.max(1, Math.ceil(items.length / 8));

  items.forEach((item, index) => {
    const x = PADDING.left + index * step + (step - barWidth) / 2;
    const totalHeight = (item.departures / max) * plotHeight;
    const overHeight = (item.above_threshold / max) * plotHeight;
    const baseHeight = Math.max(0, totalHeight - overHeight);
    const y = PADDING.top + plotHeight;

    const group = document.createElementNS(SVG_NS, "g");
    group.setAttribute("class", "af-chart__bar");

    const title = document.createElementNS(SVG_NS, "title");
    const percentage =
      item.departures > 0
        ? formatPercent((item.above_threshold / item.departures) * 100, 1)
        : "—";
    title.textContent = `${formatDateTime(item.timestamp)} · ${formatNumber(item.departures)} salidas · ${formatNumber(item.above_threshold)} superan el umbral (${percentage})`;
    group.append(title);

    if (baseHeight > 0) {
      const base = document.createElementNS(SVG_NS, "rect");
      base.setAttribute("x", String(x));
      base.setAttribute("y", String(y - baseHeight));
      base.setAttribute("width", String(barWidth));
      base.setAttribute("height", String(baseHeight));
      base.setAttribute("rx", "2");
      base.setAttribute("class", "af-chart__segment af-chart__segment--base");
      group.append(base);
    }

    if (overHeight > 0) {
      const over = document.createElementNS(SVG_NS, "rect");
      over.setAttribute("x", String(x));
      over.setAttribute("y", String(y - totalHeight));
      over.setAttribute("width", String(barWidth));
      over.setAttribute("height", String(overHeight));
      over.setAttribute("rx", "2");
      over.setAttribute("class", "af-chart__segment af-chart__segment--over");
      group.append(over);
    }

    if (index % labelEvery === 0 || index === items.length - 1) {
      const label = document.createElementNS(SVG_NS, "text");
      label.setAttribute("x", String(x + barWidth / 2));
      label.setAttribute("y", String(CHART_HEIGHT - 12));
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "af-chart__tick");
      label.textContent = shortLabel(item.timestamp, interval);
      svg.append(label);
    }

    svg.append(group);
  });

  return svg;
}

function shortLabel(timestamp, interval) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  const day = String(date.getUTCDate()).padStart(2, "0");
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  if (interval === "day") return `${day}/${month}`;
  return `${day}/${month} ${String(date.getUTCHours()).padStart(2, "0")}h`;
}
