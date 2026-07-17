# Design & methodology

Why this project is built the way it is: the provenance, the data-model and
statistical choices, and — most usefully — the decisions that were made the hard
way, with their reasons. If you are here to *run* the pipeline, see
[`AGENTS.md`](AGENTS.md); if you want the headline answer, see
[`VERDICT.md`](VERDICT.md).

---

## 1. Provenance

The question is not arbitrary — it is step 1 of a staged plan:

1. [`docs/research-brief.md`](docs/research-brief.md) — the parent research
   program. It surveyed many candidate retail edges and singled out Kalshi's
   favorite–longshot bias as the strongest *structural* one, then issued a
   staged GO: **build a read-only collector and verify the bias persists
   post-publication before committing any capital.** This repo is that step.
2. [`docs/design-spec.md`](docs/design-spec.md) — the design spec. §1 is the
   original handoff spec (data model, methodology, **pre-committed go/no-go
   criteria**); §2 is the verified-drift addendum from live-API probes (where
   reality differed — §2 wins).
3. [`docs/kalshi-api-notes.md`](docs/kalshi-api-notes.md) — verified API ground
   truth (endpoints, record shapes, rate limits, fee model). **Overrides memory
   and the spec** on any API question.

Scope boundaries (still binding): read-only, no auth, no order placement, no
longshot-side strategy work.

---

## 2. Data model

DuckDB, single file, `src`-layout Python package. Normalized tables: `series`
(authoritative category + fee model), `events` (event → series, fee overrides),
`markets` (settled markets), `trades` (the firehose), plus `stream_state` and
`collection_log` for resumable collection. Three deviations from the naive model,
each deliberate:

- **Prices are dollar-strings, counts fractional.** The API migrated off
  integer cents (Jan–Mar 2026): trades carry `yes_price_dollars` (`"0.0100"`),
  `count_fp` (`"935.19"`). Stored as `DOUBLE`; cent buckets are derived.
- **`trades` stores a closed, typed 10-field record + an `extra` JSON catch-all**
  rather than a full `raw` blob. A `raw` column would roughly triple storage
  across ~7×10⁸ rows for zero analytical value; `extra` still captures any
  future unknown key so nothing is silently dropped. `markets`/`events`/`series`
  keep full `raw` (small tables).
- **No primary key on `trades`** — see decision #7 below.

Category and fee model are **never inferred from titles**: they come from the
`series` record (`fee_type`, `fee_multiplier`), with per-event overrides applied
by `COALESCE` in `v_universe`.

---

## 3. Analysis methodology

The observation panel and every statistic are computed in DuckDB SQL over lazy
views; Python only ever sees per-event sums (a few hundred thousand rows), never
raw observations.

- **Universe** (`v_universe`): settled, `market_type='binary'`, `result ∈
  {yes,no}`, `settlement_ts ≥ 2024-01-01`, non-parlay. Everything excluded is
  counted by reason in the report's exclusion table.
- **Two observations per trade** (`v_obs`): each trade enters the panel as both
  its Yes-side and its No-side observation (Whelan-style contract counting). This
  double-counts by construction, which is exactly why **all confidence intervals
  cluster by `event_ticker`** — multi-strike events and Yes/No symmetry correlate
  outcomes within an event.
- **Fees** ([`fees.py`](src/kalshi_flb/fees.py)): taker `0.07 · mult · C · P ·
  (1−P)`, rounded **up**; maker `0` on `quadratic` series, `25%` of the taker
  formula on `quadratic_with_maker_fees`, `NaN` sentinel for `flat`/unknown
  (those rows are excluded from net-of-fee stats and counted). Rounding quantum
  is `$0.01` before the 2026-02-05 era boundary and `$0.0001` after; the boundary
  is unconfirmed by the API changelog, so the report runs a **sensitivity check**
  over both eras (it proved immaterial: ±0.001¢). The fee math has a **SQL twin**
  that is parity-tested against the Python reference on random inputs, so
  in-database aggregation and the reference implementation cannot silently drift.
- **Clustered bootstrap** ([`calibration.py`](src/kalshi_flb/calibration.py)):
  percentile CI for a ratio-of-sums, resampling **events** (B=1000, multinomial
  weights, memory-adaptive chunks).
- **Segmentation:** category (from `series`), liquidity tercile (`NTILE(3)` of
  market `volume_fp` — a post-hoc cut, so tercile-3 results are descriptive, not
  tradeable ex ante), and time-to-close (final 24h vs. earlier).
- **The decay test:** split on trade `created_time` at **2025-09-18T00:00Z**
  (SSRN publication); recompute everything pre vs. post.

The aggregation never materializes the ~1.34-billion-row expanded panel: it is
summed into an `agg_obs` event×bucket×segment table in time-partitioned passes,
and every downstream statistic and bootstrap reads `agg_obs`.

---

## 4. Decision log — what we learned the hard way (the WHYs)

1. **API drift vs. the spec** (verified day 1): prices are now dollar-strings
   with fractional counts; integer-cent fields are gone. `taker_side` is
   deprecated → we collect it plus `taker_outcome_side` (authoritative) and
   `taker_book_side`. `GET /historical/cutoff` is a **rolling ~60-day boundary**,
   not a fixed date — re-read every run.
2. **Fee metadata is data, not documentation.** `series.fee_type` /
   `fee_multiplier` (+ event overrides) are authoritative;
   `/series/fee_changes?show_historical=true` gives change history. The official
   fee PDF blocks all fetchers (Cloudflare 429), so the 0.07 taker coefficient is
   brief-sourced and third-party cross-checked, flagged in the report caveats.
   Rounding-era sensitivity proved immaterial anyway.
3. **Parlay (multivariate) markets are ~82% of market rows** and mechanically
   longshot-heavy. They post-date the paper and never enter the panel. Excluded
   at collection (`mve_filter=exclude`); their *trades* are identified by the
   `KXMVE` ticker prefix — verified an exact discriminator on 1.455M markets (0
   mismatches both directions) — and dropped at insert (counted in
   `stream_state('trades_mve_dropped')`).
4. **Scale reality: ~672M trades**, not the ~70M implied by pre-2026 literature
   — 2026 sports months run 1–3.5M trades/day. Every capacity assumption (rows,
   RAM, disk, runtime) had to be re-derived from shard watermarks mid-collection.
5. **Cursor pagination is sequential;** Kalshi's ~1.4s page latency, not our
   request pacing, is the per-cursor throughput floor. The only lever is parallel
   **disjoint time-window shards** (`min_ts`/`max_ts`), all sharing one paced
   client (~16 req/s of the ~20/s Basic budget). Server 5xxs occur under this
   concurrency; backoff absorbs them.
6. **Row-at-a-time DB writes were the original bottleneck** (~20× slower than the
   network). All writes are single-statement vectorized batches via a registered
   DataFrame.
7. **No primary key on `trades`:** an ART index over ~7×10⁸ UUIDs would exhaust
   the box's 61 GB RAM. Consequence: kill/resume overlaps produced 4.09M duplicate
   rows (0.6%), removed physically by
   [`scripts/dedupe_trades.py`](scripts/dedupe_trades.py) (month-partitioned,
   on-disk swap table — temp tables are memory-resident and don't fit the big
   months). The DQ gate verifies 0 remaining.
8. **⚠️ An unbounded DuckDB run froze the whole machine once.** Everything heavy
   is now triple-capped (connection memory limit + disk spill dir; a kernel
   cgroup cage; a disk-space self-abort). See [`AGENTS.md`](AGENTS.md) §
   machine-safety.
9. **The expanded panel is ~1.34 billion rows** (two sides × 672M). It is never
   materialized: `create_agg` aggregates it into `agg_obs` in time-partitioned
   passes (months; week-slices for months >60M trades, because one slice's
   out-of-core aggregate spills ~1–2× its input to temp disk and a single 2026
   month can be 171M trades).
10. **Methodology choices** (documented in §3 and the report): both sides of
    every trade enter the panel with event-level clustering as the double-count
    mitigation; maker returns condition on fills that actually happened (adverse
    selection is *embedded* — realistic); per-contract fees amortize each trade's
    rounded total (`fee(C)/C`); "80–97¢" is operationalized as 1¢ buckets 80–96
    (price ∈ [0.80, 0.97)); the publication split is on trade `created_time`.

---

## 5. Known limitations & what wasn't built

- **Capacity is inferred, not measured.** The optional phase-2 order-book
  snapshotter was not built, so the capacity note in [`VERDICT.md`](VERDICT.md)
  relies on market-level `volume_fp`/`liquidity_dollars` distributions, not live
  book depth. The academic authors put the ceiling at hundreds-to-low-thousands
  of dollars of working capital.
- **Fee-coefficient verification is pending** on the official PDF (429 at build
  time); the rounding-era boundary is approximate. Both are sensitivity-tested
  and flagged in the report; neither changes the verdict.
- **Fee drift:** net-of-fee stats use each series' *current* fee params. ~35% of
  panel contract volume sits on series with ≥1 recorded fee change; a time-aware
  fee join is the obvious next refinement if fee-level precision ever matters.
- **Liquidity terciles are post-hoc** (final market volume), so tercile-3
  category results — which gate the verdict — are descriptive, not an ex-ante
  tradeable filter.
