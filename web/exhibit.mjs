import {
  defaultState,
  normalizeState,
  parseState,
  serializeState,
  buildView,
} from "./exhibit-model.mjs";
import {
  renderChart,
  renderTable,
  renderLegend,
  describeDatum,
} from "./exhibit-charts.mjs";

const $ = (selector) => document.querySelector(selector);
let stats;
let state = defaultState();
let view;
let selectedDatum = null;

function selectDatum(datum) {
  selectedDatum = datum;
  $("#datum").textContent = describeDatum(selectedDatum, view);
}

function render(announce = true) {
  view = buildView(stats, state);
  selectedDatum = null;
  $("#category").value = state.category;
  $("#period").querySelector('[value="both"]').disabled =
    state.mode !== "calibration";
  $("#period").value = state.period;
  document
    .querySelectorAll("[data-mode]")
    .forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.mode === state.mode),
      ),
    );
  $("#lab-explanation").textContent = view.explanation;
  $("#lab-note").textContent = view.note;
  $("#evidence").textContent = view.caption;
  $("#method").textContent = view.method;
  $("#datum").textContent =
    "Focus, point to, or tap a plotted datum for its values. The complete values table is below.";
  renderChart($("#lab-chart"), view, selectDatum);
  renderTable($("#values"), view);
  renderLegend($("#legend"), view);
  $("#copy-fallback").hidden = true;
  if (announce) $("#announcement").textContent = view.caption;
}

function update(next) {
  state = normalizeState(next, stats);
  $("#load-status").hidden = true;
  history.pushState(null, "", serializeState(state));
  render();
}

function restore(scroll = false) {
  if (!stats) return;
  const parsed = parseState(location.hash, stats);
  if (!parsed.isLab) return;
  state = parsed.state;
  render();
  if (parsed.invalid) {
    history.replaceState(null, "", serializeState(state));
    $("#load-status").hidden = false;
    $("#load-status").textContent =
      "That shared selection was invalid. Unsupported choices were reset to the defaults shown in the controls.";
  } else $("#load-status").hidden = true;
  if (scroll)
    $("#explore").scrollIntoView({ behavior: "instant", block: "start" });
}

async function load() {
  $("#load-error").hidden = true;
  $("#load-status").hidden = false;
  $("#load-status").textContent =
    "Loading interactive controls. The saved after-publication figure remains available.";
  try {
    const response = await fetch("./data/stats.json");
    if (!response.ok)
      throw new Error(`Snapshot request failed: ${response.status}`);
    stats = await response.json();
    // Validate the interface before replacing any static evidence.
    if (
      !Array.isArray(stats.meta?.categories) ||
      !stats.curves ||
      !stats.kpi ||
      !stats.by_category
    )
      throw new Error("Invalid snapshot");
    for (const category of stats.meta.categories.toSorted((a, b) =>
      a.localeCompare(b),
    )) {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      $("#category").append(option);
    }
    state = parseState(location.hash, stats).state;
    render(false);
    $("#lab-controls").disabled = false;
    $("#reset").disabled = false;
    $("#copy-view").disabled = false;
    $("#load-status").hidden = true;
    restore(Boolean(location.hash && parseState(location.hash, stats).isLab));
  } catch {
    $("#load-status").hidden = true;
    $("#load-error").hidden = false;
    $("#announcement").textContent =
      "Interactive results could not load. The saved figure and report are available. Try loading again.";
  }
}

document
  .querySelectorAll("[data-mode]")
  .forEach((button) =>
    button.addEventListener("click", () =>
      update({ ...state, mode: button.dataset.mode }),
    ),
  );
$("#category").addEventListener("change", (event) =>
  update({ ...state, category: event.target.value }),
);
$("#period").addEventListener("change", (event) =>
  update({ ...state, period: event.target.value }),
);
$("#reset").addEventListener("click", () => update(defaultState(state.mode)));
$("#retry").addEventListener("click", load);
window.addEventListener("hashchange", () => {
  if (!stats) return;
  if (parseState(location.hash, stats).isLab) restore(true);
  else {
    state = defaultState();
    render();
    $("#load-status").hidden = true;
  }
});
$("#copy-view").addEventListener("click", async () => {
  const url = new URL(location.href);
  url.hash = serializeState(state);
  try {
    await navigator.clipboard.writeText(url.href);
    $("#announcement").textContent = "Link to this view copied.";
  } catch {
    $("#copy-fallback").hidden = false;
    $("#share-url").value = url.href;
    $("#share-url").focus();
    $("#share-url").select();
    $("#announcement").textContent =
      "Copy this view using the selected address.";
  }
});
let resizeTimer;
let printing = false;
function redrawChart() {
  if (!view) return;
  renderChart(
    $("#lab-chart"),
    view,
    selectDatum,
    selectedDatum,
    printing ? 640 : undefined,
  );
}
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(redrawChart, 100);
});
window.addEventListener("beforeprint", () => {
  printing = true;
  clearTimeout(resizeTimer);
  // PDF generation can dispatch this before print media changes the layout.
  // Use a paper-sized coordinate system independently of the screen width.
  redrawChart();
});
window.addEventListener("afterprint", () => {
  printing = false;
  redrawChart();
});
load();
