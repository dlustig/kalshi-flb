# AGENTS.md — working on this repository

Orientation for anyone (human or agent) extending or operating `kalshi-flb`.
For *why* it is built this way, read [`DESIGN.md`](DESIGN.md) first.

## Hard scope boundary (binding)

**Read-only, unauthenticated, no trading.** No order placement, no authenticated
endpoints, no longshot-side strategy code. The whole project's defensibility
rests on this — do not cross it.

## Setup

Python 3.12, [uv](https://docs.astral.sh/uv/)-managed.

```bash
uv sync            # create the environment from uv.lock
uv run pytest      # 49 tests — must stay green before any commit
```

## Operating commands

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
materialized `agg_obs` (event×bucket×segment sums — **all analysis reads this**,
never raw trades). The committed [`analysis/out/`](analysis/out/) bundle is an
example of what `report` produces from a full run.

## Conventions for changes

- **TDD.** The suite mixes known-answer stats tests, synthetic
  calibration/bias-detection tests, SQL↔Python fee parity, and collector tests
  against recorded API fixtures (`httpx.MockTransport`). Add tests with behavior.
- **API notes are ground truth.** [`docs/kalshi-api-notes.md`](docs/kalshi-api-notes.md)
  overrides memory and the spec on any endpoint/record/fee question.
- **No auto-commit.** Propose the commit message and let the human commit.
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
