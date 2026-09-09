# Research Observatory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship the approved Almost Certain field-notebook exhibit as a portable, verified static page ready for Bitbucket.

**Architecture:** Keep the existing Python research pipeline and frozen chart JSON. A small offline publication builder renders dated HTML and static SVG fallbacks from that snapshot and copies evidence into a portable `web/` bundle. Browser modules provide supported chart views and URL-state restoration; no server, framework migration, new collection, or browser-side statistical inference is required.

**Tech Stack:** Python 3.12 standard library for publication, existing uv/pytest environment, semantic HTML/CSS/SVG, native JavaScript modules, Node's built-in test runner, browser verification with Playwright.

## Global Constraints

- Read-only, unauthenticated, no trading. No authenticated market endpoints or longshot-side strategy work.
- Match the approved visual preview at `.superpowers/brainstorm/803500-1788881194/content/almost-certain-field-notebook.html`: warm paper, green ink, serif headlines, generous editorial composition, orange comparisons.
- The design document is `docs/superpowers/specs/2026-09-08-research-observatory-design.md`.
- A finished July 2026 research snapshot, not a live service or audience-growth product.
- Generated files are never hand-edited. Regenerate HTML, static SVG, evidence copies, and manifest via the builder. Existing `web/data/stats.json` remains an input; do not recompute its estimates in JavaScript.
- No automatic commits. Keep a file-based execution/review record while changes remain uncommitted. Task review packages use working diffs and new-file contents, not empty commit ranges.
- Preserve unrelated untracked `analysis/out/plots/net_edge_by_category.png`, existing GitHub workflow behavior, analytical modules, and database assets.
- New heavy DQ/analysis runs require the repository's cgroup, memory, disk, detached-execution, and logging protocol. No full report rebuild is needed for a restyle.
- Snapshot trade count is 671,921,586. Analysis generation is 2026-07-03 03:31Z per saved report. Website generation has a separate timestamp. The two-sided ~1.34B expansion is conceptual before filtering; aggregate cells number 48,759,259.
- Exactly supported exploration: calibration category/period (pre, post, both), maker/taker curves category/period (pre, post) in full favorite-side 5¢ bins, category maker headline intervals period and selected category. No invented combined filters or custom statistics.
- Missing estimates/intervals remain missing. Pooled curve intervals use 400 bootstrap replicates; headline intervals use 1,000. Curve bins 95–99¢ must not be relabeled as 95–96¢. Exact headline band is [80¢,97¢).
- Public claims retain uncertainty, observational rather than causal before/after framing, observed-fill execution limits, and retrospective liquidity/fee caveats.
- Static bundle must work at site root and under `/almost-certain/`, using relative assets and URL fragments. No project analytics or external runtime assets.
- Baseline Python tests: `.venv/bin/python -m pytest -q` — 49 passed. No existing typecheck command is configured in `pyproject.toml`; report that fact rather than inventing one. JavaScript syntax and behavior checks are separate from typechecking.

## Task 1: Snapshot publication builder and evidence

**Files:**
- Create `scripts/build_exhibit.py`, `tests/test_exhibit.py`, `web/snapshot.json`.
- Generate `web/data/manifest.json`, `web/evidence/report.md`, `web/evidence/VERDICT.md`, referenced report plots, and static SVG fallbacks from source inputs.
- Preserve `web/data/stats.json` and the analytical export script.

**Interfaces:**
- CLI: `python scripts/build_exhibit.py --out web --source-url https://github.com/dlustig/kalshi-flb` (source URL can later be set to the actual public Bitbucket repository).
- Python: `build_exhibit(repo_root: Path, out_dir: Path, source_url: str) -> dict` returns the manifest. Missing template is a clear build error; tests may supply a minimal template.
- Reads `web/exhibit.html` template, `web/exhibit.css`, browser `.mjs` files, frozen stats, snapshot metadata, and committed report artifacts.
- Template substitution markers are `{{name}}` from an explicit mapping; unknown markers fail. All prose substitutions are HTML-escaped; only generated SVG/table fragments are trusted markup.
- Required markers: `hero_svg`, `pre_interval_svg`, `post_interval_svg`, `default_lab_svg`, `default_lab_table`, `trade_count`, `trade_count_short`, `aggregate_count_short`, `snapshot_label`, `analysis_generated`, `publication_date`, `pre_net`, `post_net`, `attenuation`, `source_url`, `methodology_url`.
- Output `data/manifest.json` records schema version, input hashes and source revision, analysis date and original timestamp boundaries from report, separate build time, curve/headline bootstrap counts, static output hashes, and archived/fresh DQ status without claiming checks not run.
- Builder handles a supplied output directory without broad recursive deletion; only writes its known output files. Validate everything possible before publishing output.

- [x] Write behavior tests first: changing fixture snapshot values changes generated display/manifest consistently; missing numeric values never become zero; external source URL is validated and escaped; copied report images exist; unknown template markers fail; outputs work in a nested folder with no original DB; hashes match emitted bytes. Use small hand-checked fixtures with nulls and fractional quantities.
- [x] Run `python -m pytest tests/test_exhibit.py -q`, retain the expected missing-builder failure as RED evidence.
- [x] Implement the standard-library builder with small SVG rendering helpers for hero, fixed headline intervals, and default pooled calibration. Plot data directly from snapshot, not hard-coded empirical figures. Include accessible titles/descriptions and a table fallback. Use a fixed shared scale for pre/post headline intervals.

```python
def display_number(value, *, places=2):
    return "Unavailable" if value is None else f"{value:+.{places}f}"

def render_template(template, values):
    import re
    return re.sub(r"\{\{([a-z_]+)\}\}", lambda m: values[m[1]], template)
```

- [x] Record source metadata from the existing report, not file modification timestamps. Bundle existing archived DQ evidence if available and clearly identify its historical date; controller handles the fresh gate.
- [x] Run affected tests to GREEN, self-review, write report with commands/results, and request task-scoped review. Do not commit.

## Task 2: The finished exhibit and interactive browser behavior

**Files:**
- Create `web/exhibit.html`, `web/exhibit.css`, `web/exhibit.mjs`, `web/exhibit-charts.mjs`, `web/exhibit-model.mjs`, `tests/web/exhibit-model.test.mjs`.
- Generate replacement `web/index.html` with Task 1 builder after sources exist.

**Interfaces:**
- `exhibit.html` uses the exact Task 1 markers and loads `./exhibit.css` and `./exhibit.mjs`. The lab fetches `./data/stats.json`.
- Model exports `normalizeState(input, stats)`, `parseState(hash, stats)`, `serializeState(state)`, `defaultState(mode)`, and `buildView(stats, state)`.
- State fields: `mode` = `calibration|roles|categories`, `category` = `All|<known category>`, `period` = `both|pre|post`. Only calibration supports both. Invalid fragment values normalize with a user-facing reset notice. Category selection in category mode highlights the row and selects its evidence caption.
- `buildView` returns renderable series/rows, labels, caption, method note, and table values using only saved statistics. Missing selected-category data cannot silently display pooled evidence.
- Chart module renders SVG into a provided container from the model view, with accessible title/description and visible labels. Native table provides every plotted value and interval; pointer/focus/tap datum annotations share one selected-datum representation.
- UI owns fetch/loading/failure/retry, control updates, hash restoration, copy-link fallback, reset, and concise live announcements. Restore hash on initial load and `hashchange`; preserve normal chapter anchors. Do not precompute bootstrap in the browser.

- [x] Write Node tests first for real state/view behavior: invalid hashes recover; role mode cannot keep both periods; category selection changes estimate and event count; missing category/period yields unavailable rather than pooled data; exact bins retained; pooled and per-category CI availability differ; null values do not plot at zero; serializer round-trips escaped category names; default reset works.

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeState } from '../../web/exhibit-model.mjs';
test('role comparison cannot request both periods', () => {
  const result = normalizeState({mode:'roles',period:'both',category:'All'}, fixture);
  assert.equal(result.period, 'post');
});
```

- [x] Run `node --test tests/web/*.test.mjs` and retain failing RED output; implement the model to GREEN.
- [x] Build the actual editorial HTML and CSS matching the accepted preview. Include hero, probability illustration labeled synthetic, before/after, three-preset lab, engineering stories, methods details, and actual source/report/data links. Explain maker/taker and all important statistical limitations in context.
- [x] Add responsive layout, keyboard interactions, non-color series differentiation, reduced motion, print stylesheet, descriptive headings/captions, and a skip link. No preview toolbar or design-feedback controls in production.
- [x] Wire the interactive lab to precomputed JSON and model. Controls remain disabled until data loads; static figures and essay remain usable with JS disabled or request failure. Failure offers retry and report link. Clipboard failure exposes a selectable full URL. Selection updates plot, caption, table, units, and counts together. Category curves show no invented CI; role plots disclose full 5¢ bins and the different observed samples.
- [x] Build the site, run Node tests and JavaScript syntax checks, and validate in browser at desktop/390px. Report focused tests and known integration concerns for independent review. Do not commit.

## Task 3: Publication integration, verification, and delivery

**Files:**
- Update `README.md` with site build/preview and reproducibility levels, `docs/publishing.md` with Bitbucket deployment and generated-file ownership.
- Update `.github/workflows/pages.yml` only as needed to verify/build the bundle while preserving current GitHub deployment; no remote changes without identified destination.
- Add small CI check workflow if needed for Python and Node checks; no new application runtime.
- Update plan checklist and `docs/superpowers/verification/2026-09-08-research-observatory.md` with actual results, evidence dates, resolved review findings, and any remaining publication prerequisites.

- [x] Run required DQ gate in detached cgroup; record limitations of its wall-clock coverage requirement for the archived snapshot. Do not sync, delete data, or modify the statistical rule to make an old snapshot look current. Any publication uses a dated snapshot and its exact evidence status.
- [x] Execute `python scripts/build_exhibit.py --out web`, verify output manifests/hashes and every local link, and check generated artifacts were not hand-edited.
- [x] Run full Python suite against the final Python sources, Node tests, `.mjs` syntax checks, and `git diff --check`. Report missing configured typecheck. Avoid redundant broad test reruns without changes.
- [x] Browser-check all three modes, all category/period combinations, missing data, share URL reload/back, reset, keyboard table access, failed fetch/retry, JS disabled, 390px and desktop, reduced motion, and print. Serve under `/almost-certain/` to expose root-relative asset mistakes. Confirm no project-origin console errors or external runtime requests.
- [x] Compare opening/lab/engineering screenshots with approved mockup and correct material visual regressions.
- [x] Dispatch whole-change review on the completed implementation, including untracked files and generated artifacts. Resolve critical/important findings and perform focused re-review.
- [x] Finish with the branch-finishing skill. Preserve the uncommitted work and review ledger because the user must commit. Produce a portable release folder, ZIP and preview URL. Destination/commit authority remain absent, so the local artifact is ready and no publication is claimed.
- [ ] Once the exact Bitbucket destination and required commit authority exist, publish only the reviewed static bundle, verify the public URL, and record the result.

## Plan review

The approved design's narrative, visual composition, three supported explorations,
evidence captions, source links, static resilience, small payload, mobile/print,
and Bitbucket subdirectory support are covered above. Optional research and a
synthetic pipeline demo remain outside the first release. Existing analytics are
preserved; the change concerns publication and presentation.

The user has authorized end-to-end execution, so there is no separate execution
choice prompt. Use sequential implementers and independent reviewers while the
controller handles data-gate evidence, publishing inputs, and integration checks.
