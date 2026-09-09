import { decimal, signed, number } from "./exhibit-model.mjs";

const NS = "http://www.w3.org/2000/svg";
const colors = ["#2e6652", "#ac5035"];
function element(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes))
    node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function line(svg, x1, y1, x2, y2, attributes = {}) {
  svg.append(
    element("line", { x1, y1, x2, y2, stroke: "#cbd0bf", ...attributes }),
  );
}
function label(svg, x, y, text, attributes = {}) {
  svg.append(element("text", { x, y, ...attributes }, text));
}
function point(svg, x, y, index) {
  svg.append(
    index === 1
      ? element("rect", {
          x: x - 3.5,
          y: y - 3.5,
          width: 7,
          height: 7,
          fill: colors[index],
        })
      : element("circle", { cx: x, cy: y, r: 3.5, fill: colors[index] }),
  );
}
function intervalText(lo, hi, unit) {
  return lo !== null && hi !== null
    ? `95% interval ${decimal(lo, 3)} to ${decimal(hi, 3)}${unit}`
    : "Interval unavailable";
}

export function describeDatum(datum, view) {
  if (view.state.mode === "categories") {
    return `${datum.label === "All" ? "All categories pooled" : datum.label}: ${datum.net_c === null ? "No estimate" : `${signed(datum.net_c)}¢ per contract`}; ${intervalText(datum.lo, datum.hi, "¢")}; ${number(datum.n_events)} events; approximately ${number(datum.n)} contracts.`;
  }
  const roles = view.state.mode === "roles";
  return `${datum.series} · ${datum.bin} bucket · mean price ${decimal(datum.x)}¢ · ${roles ? `net return ${signed(datum.y)}¢ per contract` : `outcome rate ${decimal(datum.y)}%`}; ${intervalText(datum.lo, datum.hi, roles ? "¢" : "%")}; approximately ${number(datum.n)} contracts.`;
}

export function renderChart(
  container,
  view,
  onSelect,
  selectedDatum = null,
  requestedWidth = container.clientWidth,
) {
  const focusedIndex = selectedDatum
    ? [...container.querySelectorAll(".datum-hit")].indexOf(
        document.activeElement,
      )
    : -1;
  const targets = [];
  let restoringFocus = false;
  const width = Math.max(300, Math.round(requestedWidth));
  const narrow = width < 500;
  const categories = view.state.mode === "categories";
  const roles = view.state.mode === "roles";
  const height = categories ? 75 + view.rows.length * 40 : narrow ? 330 : 380;
  const svg = element("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "group",
    "aria-labelledby": "lab-plot-title lab-plot-desc",
  });
  svg.append(element("title", { id: "lab-plot-title" }, view.title));
  svg.append(
    element(
      "desc",
      { id: "lab-plot-desc" },
      `${view.caption} Focus or tap a point for its values. A complete native table follows the figure.`,
    ),
  );
  function target(datum, x, y, attributes = {}) {
    const hit = element("circle", {
      cx: x,
      cy: y,
      r: 12,
      class: "datum-hit",
      tabindex: 0,
      role: "button",
      "aria-label": describeDatum(datum, view),
      ...attributes,
    });
    function select() {
      svg
        .querySelectorAll("[data-selected]")
        .forEach((node) => node.removeAttribute("data-selected"));
      hit.setAttribute("data-selected", "true");
      onSelect(datum);
    }
    hit.addEventListener("pointerenter", select);
    hit.addEventListener("focus", () => {
      if (!restoringFocus) select();
    });
    hit.addEventListener("click", select);
    hit.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select();
      }
    });
    if (datum === selectedDatum) hit.setAttribute("data-selected", "true");
    targets.push(hit);
    svg.append(hit);
  }
  if (categories) {
    const left = narrow ? 139 : 185,
      right = width - 22,
      top = 29,
      bottom = height - 32;
    const values = view.rows
      .flatMap((r) => [r.net_c, r.lo, r.hi])
      .filter(Number.isFinite);
    const lo = Math.floor(Math.min(-1, ...values) / 5) * 5,
      hi = Math.ceil(Math.max(3, ...values) / 5) * 5;
    const x = (value) => left + ((value - lo) / (hi - lo)) * (right - left);
    label(svg, left, 12, "NET RETURN (¢ / CONTRACT)", { class: "axis-title" });
    for (let tick = 0; tick <= 4; tick++) {
      const value = lo + ((hi - lo) * tick) / 4;
      line(svg, x(value), top - 5, x(value), bottom, { stroke: "#bec8b1" });
      label(svg, x(value), height - 10, `${decimal(value, 1)}¢`, {
        "text-anchor": "middle",
      });
    }
    line(svg, x(0), top - 5, x(0), bottom, {
      stroke: "#657064",
      "stroke-dasharray": "4 4",
    });
    view.rows.forEach((row, index) => {
      const y = top + index * 40;
      if (row.selected)
        svg.append(
          element("rect", {
            x: 0,
            y: y - 15,
            width,
            height: 32,
            class: "selected-row",
          }),
        );
      const text = row.label === "All" ? "All pooled" : row.label;
      const textNode = element("text", {
        x: left - 10,
        y: y + 4,
        "text-anchor": "end",
      });
      if (narrow && text.length > 18) {
        const middle = text.lastIndexOf(" ", Math.ceil(text.length / 2) + 3);
        textNode.append(
          element("tspan", { x: left - 10, dy: -6 }, text.slice(0, middle)),
          element("tspan", { x: left - 10, dy: 13 }, text.slice(middle + 1)),
        );
      } else textNode.textContent = text;
      svg.append(textNode);
      if (row.lo !== null && row.hi !== null) {
        line(svg, x(row.lo), y, x(row.hi), y, {
          stroke: colors[0],
          "stroke-width": 2,
        });
        for (const value of [row.lo, row.hi])
          line(svg, x(value), y - 4, x(value), y + 4, { stroke: colors[0] });
      }
      if (row.net_c !== null) {
        point(svg, x(row.net_c), y, 0);
        target(row, x(row.net_c), y);
      } else label(svg, left + 8, y + 4, "No estimate");
    });
  } else {
    const left = narrow ? 44 : 53,
      right = width - 17,
      top = 33,
      bottom = height - 52;
    const all = view.series.flatMap((series) => series.points);
    const values = all
      .flatMap((r) => [r.y, r.lo, r.hi])
      .filter(Number.isFinite);
    const low = roles ? Math.floor(Math.min(0, ...values)) - 1 : 0;
    const high = roles ? Math.ceil(Math.max(0, ...values)) + 1 : 100;
    const x = (value) =>
      left + ((value - (roles ? 80 : 0)) / (roles ? 20 : 100)) * (right - left);
    const y = (value) =>
      bottom - ((value - low) / (high - low)) * (bottom - top);
    label(
      svg,
      left,
      13,
      roles ? "NET RETURN (¢ / CONTRACT)" : "OUTCOME RATE (%)",
      { class: "axis-title" },
    );
    for (let tick = 0; tick <= 5; tick++) {
      const value = low + ((high - low) * tick) / 5;
      line(svg, left, y(value), right, y(value));
      label(svg, left - 8, y(value) + 4, decimal(value, roles ? 1 : 0), {
        "text-anchor": "end",
      });
    }
    for (const value of roles
      ? [80, 85, 90, 95, 100]
      : [0, 20, 40, 60, 80, 100])
      label(svg, x(value), bottom + 24, `${value}¢`, {
        "text-anchor": "middle",
      });
    label(svg, right, height - 5, "MEAN MARKET PRICE →", {
      class: "axis-title",
      "text-anchor": "end",
    });
    if (roles)
      line(svg, left, y(0), right, y(0), {
        stroke: "#657064",
        "stroke-dasharray": "4 4",
      });
    else {
      line(svg, x(0), y(0), x(100), y(100), {
        stroke: "#89947e",
        "stroke-dasharray": "5 5",
      });
      label(svg, x(43), y(28), "Perfect calibration", { "font-size": 11 });
    }
    for (const series of view.series) {
      const index = roles ? series.index : series.period === "post" ? 1 : 0;
      for (const segment of series.segments)
        svg.append(
          element("polyline", {
            points: segment.map((p) => `${x(p.x)},${y(p.y)}`).join(" "),
            stroke: colors[index],
            class: "plot-line",
            "stroke-dasharray": index ? "6 3" : "none",
          }),
        );
      for (const datum of series.points) {
        if (datum.lo !== null && datum.hi !== null) {
          line(svg, x(datum.x), y(datum.lo), x(datum.x), y(datum.hi), {
            stroke: colors[index],
            opacity: 0.55,
          });
          for (const value of [datum.lo, datum.hi])
            line(svg, x(datum.x) - 3, y(value), x(datum.x) + 3, y(value), {
              stroke: colors[index],
              opacity: 0.55,
            });
        }
        point(svg, x(datum.x), y(datum.y), index);
      }
    }
    // Hit targets are drawn last so every point stays reachable above the lines.
    for (const series of view.series)
      for (const datum of series.points) target(datum, x(datum.x), y(datum.y));
    if (!all.length)
      label(
        svg,
        (left + right) / 2,
        (top + bottom) / 2,
        "No estimate for this selection",
        { "text-anchor": "middle" },
      );
  }
  container.replaceChildren(svg);
  if (focusedIndex >= 0) {
    // A resize keeps the same view and datum order. Restore focus without
    // changing a selection that may have subsequently moved with the pointer.
    restoringFocus = true;
    targets[focusedIndex]?.focus({ preventScroll: true });
    restoringFocus = false;
  }
}

export function renderTable(container, view) {
  const table = document.createElement("table");
  const caption = table.createCaption();
  caption.textContent = `${view.label} · ${view.title}`;
  const head = table.createTHead().insertRow();
  for (const heading of view.table.headers) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = heading;
    head.append(cell);
  }
  const body = table.createTBody();
  for (const values of view.table.rows) {
    const row = body.insertRow();
    values.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      row.append(cell);
    });
  }
  container.replaceChildren(table);
}

export function renderLegend(container, view) {
  container.replaceChildren();
  const labels =
    view.state.mode === "categories"
      ? [{ label: "Maker · exact [80¢, 97¢) band", index: 0 }]
      : view.series.map((s) => ({
          label: s.label,
          index:
            view.state.mode === "roles" ? s.index : s.period === "post" ? 1 : 0,
        }));
  for (const item of labels) {
    const span = document.createElement("span");
    const svg = element("svg", { viewBox: "0 0 27 12", "aria-hidden": "true" });
    line(svg, 0, 6, 27, 6, {
      stroke: colors[item.index],
      "stroke-width": 2,
      "stroke-dasharray": item.index ? "5 3" : "none",
    });
    point(svg, 13, 6, item.index);
    span.append(svg, document.createTextNode(item.label));
    container.append(span);
  }
}
