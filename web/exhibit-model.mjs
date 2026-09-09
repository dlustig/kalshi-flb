const MODES = ["calibration", "roles", "categories"];
const finite = (value) => (Number.isFinite(value) ? value : null);
export const number = (value) =>
  Number.isFinite(value) ? value.toLocaleString("en-US") : "Unavailable";
export const decimal = (value, digits = 2) =>
  Number.isFinite(value) ? value.toFixed(digits) : "Unavailable";
export const signed = (value) =>
  Number.isFinite(value)
    ? `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(3)}`
    : "Unavailable";
const interval = (lo, hi) =>
  lo !== null && hi !== null
    ? `${decimal(lo, 3)} to ${decimal(hi, 3)}`
    : "Unavailable";
const periodName = (period) =>
  period === "pre" ? "Before publication" : "After publication";

export function defaultState(mode = "calibration") {
  mode = MODES.includes(mode) ? mode : "calibration";
  return {
    mode,
    category: "All",
    period: mode === "calibration" ? "both" : "post",
  };
}

export function normalizeState(input = {}, stats) {
  const defaults = defaultState(input.mode);
  return {
    mode: defaults.mode,
    category: ["All", ...stats.meta.categories].includes(input.category)
      ? input.category
      : "All",
    period: (defaults.mode === "calibration"
      ? ["both", "pre", "post"]
      : ["pre", "post"]
    ).includes(input.period)
      ? input.period
      : defaults.period,
  };
}

export function parseState(hash, stats) {
  const fragment = hash.replace(/^#/, "");
  const isLab = fragment.includes("=") || fragment.includes("&");
  if (!isLab) return { state: defaultState(), invalid: false, isLab: false };
  const params = new URLSearchParams(fragment);
  const input = Object.fromEntries(params);
  const state = normalizeState(input, stats);
  const invalid =
    [...params.keys()].some(
      (k) => !["mode", "category", "period"].includes(k),
    ) ||
    [...params.keys()].some((k) => params.getAll(k).length > 1) ||
    Object.entries(input).some(([k, v]) => state[k] !== v);
  return { state, invalid, isLab: true };
}

export function serializeState(state) {
  return `#${new URLSearchParams({ mode: state.mode, category: state.category, period: state.period })}`;
}

function headline(row, label, selected) {
  return {
    label,
    selected,
    net_c: finite(row?.net_c),
    lo: finite(row?.ci_lo),
    hi: finite(row?.ci_hi),
    n: finite(row?.n),
    n_events: finite(row?.n_events),
  };
}

export function buildView(stats, input) {
  const state = normalizeState(input, stats);
  const categoryName =
    state.category === "All" ? "All categories pooled" : state.category;
  const label = `${categoryName} · ${state.period === "both" ? "Before & after publication" : periodName(state.period)}`;
  if (state.mode === "categories") {
    const rows = [
      "All",
      ...stats.meta.categories.toSorted((a, b) => a.localeCompare(b)),
    ].map((category) =>
      headline(
        category === "All"
          ? stats.kpi[state.period]
          : stats.by_category[state.period]?.find((r) => r.label === category),
        category,
        category === state.category,
      ),
    );
    const selected = rows.find((r) => r.selected);
    const caption =
      selected.net_c === null
        ? `${label} · No estimate for this selection.`
        : `${label} · Maker · 80¢ ≤ price < 97¢. Estimated net return ${signed(selected.net_c)}¢ per contract. ${selected.lo === null || selected.hi === null ? "Interval unavailable" : `95% interval: ${interval(selected.lo, selected.hi)}¢`}. ${number(selected.n_events)} ${selected.n_events === 1 ? "event" : "events"}; approximately ${number(selected.n)} contracts.`;
    return {
      state,
      title: "Maker return by category",
      label,
      rows,
      selected,
      series: [],
      caption,
      explanation:
        "A dot is an estimate; its line is a 95% uncertainty interval. Categories stay alphabetical. Select a category to highlight its evidence.",
      note: "Exact headline band: 80¢ inclusive to 97¢ exclusive. Event counts matter, especially for small categories.",
      method:
        "Headline intervals resample events with 1,000 bootstrap replicates. Fewer than two events: interval unavailable. Category inspection is exploratory. Contract quantity is approximate, not a count of independent observations; events may contribute to multiple groups.",
      table: {
        headers: [
          "Category",
          "Net ¢ / contract",
          "95% interval ¢",
          "Events",
          "Approx. contracts",
        ],
        rows: rows.map((r) => [
          r.label === "All" ? "All categories pooled" : r.label,
          signed(r.net_c),
          interval(r.lo, r.hi),
          number(r.n_events),
          number(r.n),
        ]),
      },
    };
  }
  const roles = state.mode === "roles";
  const specs = roles
    ? ["maker", "taker"].map((role) => ({
        period: state.period,
        role,
        label: role === "maker" ? "Maker" : "Taker",
      }))
    : (state.period === "both" ? ["pre", "post"] : [state.period]).map(
        (period) => ({ period, role: "all", label: periodName(period) }),
      );
  const valueKey = roles ? "net_c" : "win_pct",
    lowKey = roles ? "net_lo" : "win_lo",
    highKey = roles ? "net_hi" : "win_hi";
  const series = specs.map((spec, index) => {
    const source = (
      stats.curves[`${spec.period}|${spec.role}|${state.category}`] || []
    )
      .filter((r) => !roles || r.bucket >= 80)
      .toSorted((a, b) => a.bucket - b.bucket);
    const rows = source.map((r) => ({
      bucket: r.bucket,
      bin: `${r.bucket}–${r.bucket + 4}¢`,
      x: finite(r.price_c),
      y: finite(r[valueKey]),
      lo: finite(r[lowKey]),
      hi: finite(r[highKey]),
      n: finite(r.n),
      series: spec.label,
    }));
    const points = rows.filter((r) => r.x !== null && r.y !== null);
    const segments = [];
    for (const point of points) {
      const last = segments.at(-1);
      if (!last || point.bucket !== last.at(-1).bucket + 5)
        segments.push([point]);
      else last.push(point);
    }
    return { ...spec, index, rows, points, segments };
  });
  const available = series.filter((s) => s.points.length).map((s) => s.label);
  const missing = series.filter((s) => !s.points.length).map((s) => s.label);
  const uncertainty =
    state.category === "All"
      ? "Whiskers: 95% event-bootstrap intervals (400 replicates)."
      : "Point estimates only. Interval not computed for this category curve.";
  return {
    state,
    title: roles ? "Maker and taker returns" : "Price meets outcomes",
    label,
    series,
    rows: [],
    caption: `${label} · ${available.length ? (roles ? "Maker versus taker · full 80–84¢, 85–89¢, 90–94¢ and 95–99¢ bins. " : "All roles · contract-weighted outcomes. ") + uncertainty : "No estimate for this selection."}${missing.length && available.length ? ` No estimate: ${missing.join(", ")}.` : ""}`,
    explanation: roles
      ? "Makers post offers; takers accept available ones. These are modeled net returns on observed trade sides after fees."
      : "Each point compares the average price in a 5¢ bucket with the outcomes that followed. Above the diagonal, outcomes occurred more often than prices implied.",
    note: roles
      ? "Role samples differ. This is not a fees-only comparison. Full 95–99¢ curve bins differ from the exact headline band [80¢, 97¢)."
      : "The full price range is descriptive calibration. It is not a strategy exploration. Missing bins are not connected.",
    method:
      "Saved statistics only; no browser-side inference. Pooled curve intervals use 400 event-bootstrap replicates; category curves have no intervals. Headline intervals use 1,000 replicates. Approximate contract quantities are weights, not independent observations. Per-bucket event counts are not exported.",
    table: {
      headers: [
        "Series",
        "Price bin",
        "Mean price ¢",
        roles ? "Net ¢ / contract" : "Outcome %",
        roles ? "95% interval ¢" : "95% interval %",
        "Approx. contracts",
      ],
      rows: series.flatMap((s) =>
        s.rows.map((r) => [
          s.label,
          r.bin,
          decimal(r.x),
          decimal(r.y, roles ? 3 : 2),
          interval(r.lo, r.hi),
          number(r.n),
        ]),
      ),
    },
  };
}
