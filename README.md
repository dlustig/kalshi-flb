# kalshi-flb

**A read-only pipeline that answers one pre-committed question with confidence
intervals: does Kalshi's favorite–longshot bias survive publication, net of
fees?**

Prediction-market prices are biased — longshots are overpriced, favorites
underpriced (Bürgi, Deng & Whelan, SSRN 2025). The authors warned that
publishing the finding might erode it. This project collects **672 million
trades** from Kalshi's public API into DuckDB and measures whether the
favorite-side **maker** edge at 80–97¢ still exists after the 2025-09-18
publication date — pre-committing to a go/no-go rule *before* looking at the
numbers.

No trading, no authentication, no order placement. Just the measurement.

---

## The answer: GO — attenuated ~62%, and not in sports

The edge survives, but only for makers, mostly outside sports, and roughly a
third of its former size.

| Maker net EV, 80–97¢ | point estimate | clustered 95% CI | n |
|---|---:|:---:|---|
| **Pre**-publication  | **+2.13¢** / contract | [+0.40, +3.59] | — |
| **Post**-publication | **+0.81¢** / contract | [−0.03, +1.60] | 15.3B contracts, 287,770 events |

The pooled post-publication interval *grazes* zero — but the pre-committed GO
criterion (a CI-positive edge in ≥1 liquid category) is met in multiple
non-sports categories: **Politics +5.7¢, Economics +5.3¢, Crypto +1.3¢** (the
most robust estimate — 1.9B contracts across 130k events), and more. Three
findings from the segmentation:

- **Sports — the volume majority — shows no edge** and drags the pooled number
  toward zero.
- **Takers lose everywhere** (−1 to −3¢ net). The maker/taker asymmetry from the
  paper is fully intact; maker-only execution is not optional.
- The edge concentrates in trades placed **>24h before close** (+2.1¢,
  CI-positive), not in the final-day scramble.

→ One-page verdict: [`VERDICT.md`](VERDICT.md) · Full analysis (calibration
tables, net-return curves, segmentation, sensitivity, exclusions, caveats):
[`analysis/out/report.md`](analysis/out/report.md).

---

## Architecture

```
Kalshi public API (no auth)
      │   paced ~16 req/s · cursor pagination · blind exponential backoff (no Retry-After)
      │   parallel disjoint time-window shards · per-shard failure isolation · resumable cursors
      ▼
  collector ──► DuckDB  (series · events · markets · trades ≈672M rows / ≈72 GB)
      │
      │   lazy SQL views:
      │     v_universe — settled binary non-parlay markets + category/fee metadata
      │     v_obs      — every trade → its Yes-side and No-side role-tagged observation
      ▼
  time-partitioned aggregation ──► agg_obs  (event × bucket × segment sums)
      │   the ~1.34-billion-row expanded panel is NEVER materialized
      ▼
  event-clustered bootstrap (B=1000) ──► report.md · plots · VERDICT.md
```

| Module | Responsibility |
|---|---|
| [`api.py`](src/kalshi_flb/api.py) | Thread-safe paced HTTP client; blind exponential backoff; cursor pagination that survives empty-page-with-cursor anomalies |
| [`db.py`](src/kalshi_flb/db.py) | Schema, dollar-string parsers, vectorized batch writes, per-stream cursor state, memory-capped connections |
| [`collector.py`](src/kalshi_flb/collector.py) | Resumable streams; ~50 disjoint time-window trade shards walked in parallel with failure isolation, retry rounds, and a disk guard |
| [`fees.py`](src/kalshi_flb/fees.py) | Fee engine (rounding eras, maker/taker) with a **SQL twin parity-tested** against the Python reference |
| [`panel.py`](src/kalshi_flb/panel.py) | Lazy observation-panel views + time-partitioned `agg_obs` materialization + exclusion accounting |
| [`calibration.py`](src/kalshi_flb/calibration.py) | Bucket stats + event-clustered percentile bootstrap; `headline()` = the deliverable statistic |
| [`report.py`](src/kalshi_flb/report.py) | `report.md` + plots + **mechanical** application of the go/no-go criteria → `VERDICT.md` |

### Engineering worth noting

- **Billion-row analysis on a memory-constrained box.** The expanded panel is
  ~1.34B rows; it is never materialized. Aggregation runs in DuckDB in
  time-partitioned passes (week-slices for 100M+ trade months) with a hard
  memory cap, a disk-spill directory, and a self-abort — after an early
  unbounded run froze the machine (see [`DESIGN.md`](DESIGN.md) §4).
- **The API's real bottleneck is per-cursor latency, not the rate limit.** A
  single cursor is sequential at ~1.4s/page, so the collector parallelizes
  *disjoint time-window shards* over one shared paced client, with each shard
  isolated, logged, and retried independently.
- **Statistically honest CIs.** Outcomes within an event are correlated (Yes/No
  symmetry, multi-strike events), so every interval is an event-clustered
  bootstrap — naive binomial CIs would overstate significance.
- **Pre-committed criteria, applied by code.** The go/no-go rule was fixed in
  the spec; `report.py` applies it mechanically — no post-hoc goalpost-moving.
- **49 tests:** known-answer statistics, synthetic calibration/bias-detection,
  SQL↔Python fee parity, and collector logic against recorded API fixtures.

---

## Reproduce

```bash
uv sync
uv run pytest                          # 49 tests

uv run kalshi-flb status               # DB + per-stream collection state
uv run kalshi-flb backfill --rps 16    # full collect from the public API (resumable; hours)
uv run python scripts/dq_check.py      # data-quality gate — run before trusting analysis
uv run kalshi-flb report               # rebuild agg_obs + report.md + VERDICT.md
```

The DuckDB file (≈72 GB) is gitignored — it rebuilds from the public API. The
committed [`analysis/out/`](analysis/out/) bundle is exactly what `report`
produced from the full run, so the result is inspectable without re-collecting.

> ⚠️ The heavy commands scan ~5×10⁸ rows. On a memory-constrained machine, run
> them under the cgroup cage described in [`AGENTS.md`](AGENTS.md) — an uncaged
> run has frozen this box before.

---

## Layout

```
kalshi-flb/
├── VERDICT.md              the one-page answer
├── DESIGN.md               methodology + the decision-log "WHYs" + provenance
├── AGENTS.md               operating commands + machine-safety protocol
├── analysis/out/           committed evidence: report.md, VERDICT.md, plots/
├── docs/                   design-spec.md, kalshi-api-notes.md, research-brief.md
├── src/kalshi_flb/         api · db · collector · fees · panel · calibration · report · cli
├── scripts/                dq_check.py, dedupe_trades.py
└── tests/                  49 tests
```

**Stack:** Python 3.12 (uv), DuckDB, httpx, numpy, pandas, matplotlib.

**Further reading:** [`DESIGN.md`](DESIGN.md) for the methodology and the
hard-won decisions · [`docs/design-spec.md`](docs/design-spec.md) for the spec
and verified API-drift addendum · [`docs/research-brief.md`](docs/research-brief.md)
for why Kalshi was the chosen edge.
