# AGENTS.md — working on this repository

**Almost Certain** is a finished personal portfolio experiment: a frozen July
2026 prediction-market research snapshot presented as an interactive field
notebook. The Python package is still named `kalshi-flb`. The goal is to show
curiosity, engineering judgment, and clear explanation—not attract users, run a
live service, or build a trading product.

## Start here: route by task

Read the relevant reference before changing its area. Keep this file as the
entry point; maintain detailed explanations in the documents below.

| Task or question | Read first |
|---|---|
| Understand the question, result, or project architecture | [`README.md`](README.md) |
| Change statistics, fees, exclusions, or interpretation | [`DESIGN.md`](DESIGN.md), especially methodology and limitations; [`VERDICT.md`](VERDICT.md) for the original decision rule and saved result |
| Investigate performance, memory, or collection tradeoffs | [`DESIGN.md`](DESIGN.md), decision log: vectorized writes, cursor sharding, index costs, deduplication, and the machine freeze; safety protocol below |
| Change API collection or record parsing | [`docs/kalshi-api-notes.md`](docs/kalshi-api-notes.md), the dated, verified API reference |
| Edit, preview, regenerate, or publish the exhibit | [`docs/publishing.md`](docs/publishing.md), including source ownership and reproduction limits |
| Understand visual intent and portfolio scope | [Exhibit design](docs/superpowers/specs/2026-09-08-research-observatory-design.md); this is historical design context, not current deployment instructions |
| Trace the original research motivation | [`docs/research-brief.md`](docs/research-brief.md) and [`docs/design-spec.md`](docs/design-spec.md); historical context does not authorize trading or expanding the project |

For current publishing behavior, use the publishing guide and workflows rather
than historical plans. If code and documentation disagree, verify the behavior
and report the discrepancy instead of silently choosing a new architecture.

## Hard scope boundary (binding)

**Read-only, unauthenticated, no trading.** No order placement, no authenticated
endpoints, no longshot-side strategy code. The whole project's defensibility
rests on this — do not cross it.

## Everyday development (no research database required)

Python 3.12, [uv](https://docs.astral.sh/uv/)-managed; Node 22 for browser checks.
Run from the repository root:

```bash
uv sync --frozen                       # install the locked environment
uv run --frozen mypy                   # package + exhibit-builder typecheck
uv run --frozen pytest                 # analysis + publication tests
node --test tests/web/*.test.mjs        # browser model tests
uv run --frozen python scripts/build_exhibit.py --out dist/site
python -m http.server --bind 127.0.0.1 8000 --directory dist/site
```

The site builder uses saved files and the Python standard library; it does not
open DuckDB or contact Kalshi. A copy, layout, or interaction change does **not**
require collection, DQ, a new report, or a new statistical export. CI commands,
including JavaScript syntax checks, live in
[`.github/workflows/checks.yml`](.github/workflows/checks.yml).

## Research operations (expensive; not routine verification)

Only run these when the task intentionally requires database work. Heavy commands
below are command references, **not safe bare invocations**: use the machine-safety
protocol before starting them. Check disk capacity before an export as well.

```bash
uv run kalshi-flb status                  # tables, per-stream state, trades-hist ETA
uv run kalshi-flb sync   --rps 8          # top up live tier + metadata (resumable)
uv run kalshi-flb backfill --rps 16       # full backfill (resumable; only if extending the window)
uv run python scripts/dq_check.py         # DATA-QUALITY GATE — run before trusting any analysis
uv run kalshi-flb report                  # rebuild agg_obs (~40 min) + report.md + VERDICT.md
uv run kalshi-flb export                  # per-table parquet dump
```

Collection is resumable: every stream persists its cursor after each page, so any
run can be killed and rerun. After a `sync` that adds trades, the sequence is
**`dq_check` → (dedupe only if it reports duplicates) → `report`**.

## ⚠️ Machine-safety protocol (non-negotiable on a memory-constrained box)

An **uncapped analysis run once froze the machine**. Analysis scans ~5×10⁸ rows;
DuckDB's out-of-core aggregation can transiently spill tens of GB. Keep every
layer of defense:

1. `db.connect()` always sets `memory_limit='12GB'`, `threads=8`,
   `preserve_insertion_order=false`, and a `temp_directory` spill dir. Do not
   remove these.
2. Run every heavy step (backfill / sync / report / dq / dedupe) inside a kernel
   cgroup cage so the worst case is the kernel killing that cgroup, not the box:
   ```bash
   systemd-run --user --scope -p MemoryMax=24G -p MemorySwapMax=0 --unit=<name> -- \
     bash -c 'setsid nohup <cmd> > <log> 2>&1 < /dev/null &'
   ```
3. Watch disk during aggregation/dedupe (`create_agg` self-aborts below 12 GB
   free). If a run dies, delete orphaned `*.tmp` spill files in
   `data/duckdb_tmp/`.
4. Detach anything long-running from the session (`setsid nohup`), log to a file,
   and poll the log — session restarts kill session-managed tasks.

## Data assets

`data/kalshi.duckdb` (≈72 GB) is **gitignored** — it is the expensive artifact,
rebuilt from the public API via `backfill`. Key tables: `trades` (~672M rows,
2024-01-01 →, no PK by design, parlay trades dropped at collection), `markets`,
`events`, `series` (authoritative category + fee model), `fee_changes`, and the
materialized `agg_obs` (event×bucket×segment sums). Statistical estimates use
`agg_obs`, not repeated raw-trade scans; maintenance and export paths may still
read raw tables. The committed [`analysis/out/`](analysis/out/) bundle is an
example of what `report` produces from a full run.

## Exhibit ownership and evidence

- Edit `web/exhibit.html`, `web/exhibit.css`, and the `web/*.mjs` source modules.
  Never hand-edit generated `web/index.html`, `web/data/manifest.json`, evidence
  copies, or generated SVGs. Run
  `uv run --frozen python scripts/build_exhibit.py --out web` to refresh committed
  preview artifacts; see the publishing guide for the full owner map.
- Preserve `web/data/stats.json` and `web/snapshot.json` during presentation-only
  changes. Re-export statistics only for an intentional research update.
- Keep the snapshot date separate from the website build date. A rebuilt page
  is not fresh research; reproducing the display is not reproducing the dataset.
- Retain uncertainty intervals, missing-value labels, and limitations. Observed
  fills are not proof of achievable execution; the before/after comparison does
  not establish that publication caused the change.
- Run the DQ gate before trusting new analysis. Preserve its actual result: a
  frozen snapshot can fail current-month coverage, and an archived PASS must
  never be presented as a fresh PASS. Do not rerun DQ for a website-only edit.

## Conventions for changes

- **TDD.** The suite mixes known-answer stats tests, synthetic
  calibration/bias-detection tests, SQL↔Python fee parity, and collector tests
  against recorded API fixtures (`httpx.MockTransport`). Add tests with behavior.
- **API notes are ground truth.** [`docs/kalshi-api-notes.md`](docs/kalshi-api-notes.md)
  overrides memory and the spec on any endpoint/record/fee question.
- **No auto-commit.** Propose the commit message and let the human commit.
- **No commit hooks.** Do not add or configure them. Run checks explicitly and
  in CI. Before any authorized commit, run the typecheck and affected tests;
  never add automated agent-authorship trailers.
- **Run the DQ gate** before regenerating or trusting the report.

## Code map

| Path | Responsibility |
|---|---|
| `src/kalshi_flb/api.py` | Thread-safe paced HTTP client; blind exponential backoff; cursor pagination |
| `src/kalshi_flb/db.py` | Schema, dollar-string parsers, vectorized batch writes, stream state |
| `src/kalshi_flb/collector.py` | Resumable streams; parallel disjoint trade shards with failure isolation + disk guard |
| `src/kalshi_flb/fees.py` | Fee engine (Python + parity-tested SQL twin) |
| `src/kalshi_flb/panel.py` | Lazy `v_universe`/`v_obs` views; `agg_obs` materialization; exclusion accounting |
| `src/kalshi_flb/calibration.py` | Bucket stats + event-clustered bootstrap; the `headline()` statistic |
| `src/kalshi_flb/report.py` | `report.md` + plots + mechanical go/no-go → `VERDICT.md` |
| `src/kalshi_flb/cli.py` | `backfill` / `sync` / `status` / `export` / `report` |
| `scripts/dq_check.py` | Data-quality gate (exits nonzero on failure) |
| `scripts/dedupe_trades.py` | Month-partitioned physical dedupe of kill/resume overlaps |
| `scripts/build_site_data.py` | Statistical export to `web/data/stats.json`; requires the research database |
| `scripts/build_exhibit.py` | Database-free static publication builder and evidence manifest |
| `web/exhibit.html`, `web/exhibit.css` | Editorial template, responsive layout, and print styling |
| `web/exhibit-model.mjs`, `web/exhibit-charts.mjs`, `web/exhibit.mjs` | View preparation, SVG charts, and controls/URL state; see publishing guide for ownership |
| `tests/`, `tests/web/` | Python research/publication checks and browser model tests |
| `.github/workflows/` | Verification and GitHub Pages deployment |
