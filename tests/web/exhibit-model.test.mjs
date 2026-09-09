import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  normalizeState,
  parseState,
  serializeState,
  defaultState,
  buildView,
} from "../../web/exhibit-model.mjs";

const stats = JSON.parse(
  readFileSync(new URL("../../web/data/stats.json", import.meta.url)),
);

test("invalid fragments recover and ordinary chapter anchors are preserved", () => {
  const parsed = parseState(
    "#mode=invalid&category=Nope&period=tomorrow",
    stats,
  );
  assert.deepEqual(parsed.state, {
    mode: "calibration",
    category: "All",
    period: "both",
  });
  assert.equal(parsed.invalid, true);
  assert.equal(parseState("#machinery", stats).isLab, false);
  assert.equal(
    parseState("#mode=calibration&category=%E0%A4%A", stats).invalid,
    true,
  );
});
test("role comparisons normalize unsupported both periods to after", () => {
  assert.equal(
    normalizeState({ mode: "roles", period: "both", category: "All" }, stats)
      .period,
    "post",
  );
});
test("category selection changes the selected estimate and event count", () => {
  const view = buildView(stats, {
    mode: "categories",
    period: "post",
    category: "Crypto",
  });
  assert.equal(view.selected.net_c, 1.311);
  assert.equal(view.selected.n_events, 130197);
  assert.equal(view.rows.find((r) => r.label === "Crypto").selected, true);
  assert.equal(view.rows[0].label, "All");
});
test("missing headline is unavailable rather than pooled and single-event CI stays missing", () => {
  const post = buildView(stats, {
    mode: "categories",
    period: "post",
    category: "Education",
  });
  assert.equal(post.selected.net_c, null);
  assert.match(post.caption, /No estimate/);
  const pre = buildView(stats, {
    mode: "categories",
    period: "pre",
    category: "Education",
  });
  assert.equal(pre.selected.n_events, 1);
  assert.equal(pre.selected.lo, null);
});
test("favorite role curves retain literal 95–99 bins and plotted intervals in table", () => {
  const view = buildView(stats, {
    mode: "roles",
    period: "post",
    category: "All",
  });
  assert.deepEqual(
    view.series[0].points.map((p) => p.bucket),
    [80, 85, 90, 95],
  );
  assert.equal(view.series[0].points.at(-1).bin, "95–99¢");
  assert.equal(view.table.rows.length, 8);
  assert.ok(view.series[0].points[0].lo !== null);
  assert.ok(view.table.headers.some((h) => h.includes("interval")));
});
test("category curves do not inherit pooled intervals and sparse bins remain separate", () => {
  const view = buildView(stats, {
    mode: "calibration",
    period: "pre",
    category: "Education",
  });
  assert.equal(view.series[0].points[0].lo, null);
  assert.deepEqual(
    view.series[0].segments.map((s) => s.map((p) => p.bucket)),
    [
      [0, 5, 10, 15],
      [80, 85, 90, 95],
    ],
  );
});
test("null curve estimates do not plot at zero or bridge the missing point", () => {
  const fixture = structuredClone(stats);
  fixture.curves["pre|all|All"][1].win_pct = null;
  const view = buildView(fixture, {
    mode: "calibration",
    period: "pre",
    category: "All",
  });
  assert.equal(view.series[0].points.length, 19);
  assert.equal(view.series[0].segments[0].length, 1);
  assert.equal(view.table.rows[1][3], "Unavailable");
});
test("shared state round trips escaped category names", () => {
  const fixture = structuredClone(stats);
  fixture.meta.categories.push("A & B / café");
  const state = { mode: "categories", period: "pre", category: "A & B / café" };
  assert.deepEqual(parseState(serializeState(state), fixture).state, state);
});
test("reset supplies documented defaults for each preset", () => {
  assert.deepEqual(defaultState(), {
    mode: "calibration",
    category: "All",
    period: "both",
  });
  assert.deepEqual(defaultState("roles"), {
    mode: "roles",
    category: "All",
    period: "post",
  });
  assert.deepEqual(defaultState("categories"), {
    mode: "categories",
    category: "All",
    period: "post",
  });
});
