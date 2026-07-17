# Kalshi Favorite–Longshot Bias Verifier — Design Spec

> Provenance: this is the handoff spec delivered 2026-07-01, preserved verbatim in
> §1, with a verified-drift addendum in §2 from live-API probes and docs research
> performed the same day. The parent document is
> [`research-brief.md`](research-brief.md) (§14 "Deep Dive — Kalshi Maker-Side
> Mechanics" contains the GO decision this project implements step 1 of).

## §1 Handoff spec (verbatim)

### Purpose
Answer ONE question before any capital is committed: **does the favorite–longshot bias documented by Bürgi, Deng & Whelan (~314k contracts, data through ~2025) still exist in current Kalshi data, net of fees, after the paper's publication?**

This is a read-only, no-auth, no-trading project. Output is a go/no-go answer with confidence intervals, not a bot.

### Context for the implementing agent
- The bias: contracts priced <20¢ historically win less often than their price implies (5¢ contracts win ~4.2%); contracts >80¢ win more often (95¢ contracts win ~95.8%). Makers outperform takers. The strategy under evaluation is *favorite-side maker orders only*.
- The authors explicitly flagged that publication (Sept 2025) may cause the anomaly to decay. The core deliverable is a **pre- vs. post-publication comparison**.
- All required data is public. The Kalshi API needs no authentication for market data. Authoritative docs: https://docs.kalshi.com — verify every endpoint signature there before coding; details below are from July 2026 research and may drift.

### Architecture
Single Python project (or TypeScript if preferred — Python suggested for the stats stack). Storage: **DuckDB** (single file DB) with Parquet export. Three components:

1. **Backfill collector** — settled markets + their trades from the historical tier.
2. **Live snapshotter** (phase 2, optional for the core question) — periodic order-book snapshots of active markets, for later maker-fill simulation.
3. **Analysis notebook/module** — calibration curves, net-of-fee returns, decay test.

### Data model (DuckDB tables)
```
markets(ticker PK, event_ticker, series_ticker, category, title,
        open_ts, close_ts, settle_ts, result,            -- 'yes'/'no'
        strike_info, raw JSON)

trades(trade_id PK, ticker FK, ts, yes_price_cents, no_price_cents,
       count, taker_side,                                 -- 'yes'/'no' — Kalshi reports this directly
       raw JSON)

collection_log(run_id, endpoint, cursor, ts, rows, status) -- resumability + audit
```
Notes:
- `taker_side` is the crown jewel: Kalshi's trade data directly identifies which side was the taker, eliminating trade-signing inference error. Preserve it exactly.
- Keep `raw` JSON columns; schema on the API side may carry fields we'll want later.

### Collection plan

#### Endpoints (verify at docs.kalshi.com; these are current as of research)
- `GET /historical/cutoff` — timestamp separating live vs. historical tiers (split introduced 2026-02-19). Read this FIRST; route queries accordingly.
- `GET /historical/markets` — settled markets older than cutoff. Cursor-paginated (`cursor`, `limit`; /markets pages up to 1,000).
- `GET /historical/trades` — public trades for settled markets.
- `GET /markets`, `GET /markets/trades` — recently settled (post-cutoff) markets/trades.
- `GET /series`, `GET /events` — category/series metadata for segmentation.

#### Scope
- Target window: **all settled markets from 2024-01-01 through present.** This brackets the paper's sample end and gives ≥9 months post-publication (Oct 2025 → Jul 2026).
- Collect ALL categories; segmentation happens in analysis. Expect sports to dominate raw volume (~85–92%) — do not let it silently swamp the panel.

#### Rate-limit budget (token bucket; Basic tier)
- Default request cost 10 tokens; Basic-tier refill is modest — design for **sustained ~single-digit requests/sec**, exponential backoff on 429 (no Retry-After header is provided).
- Full backfill will take hours-to-days at Basic tier. Make the collector **resumable by cursor** (persist cursors in `collection_log`), idempotent (upsert on PK), and safe to run as a long-lived cron/loop.
- Do NOT hammer: one worker, polite pacing. If volume warrants, the Advanced tier is a self-serve API upgrade.

### Analysis plan (mirror the Whelan methodology, then extend)

#### Core calibration
1. For every settled market, join trades → outcome. Each trade yields two observations (Yes side at `yes_price`, No side at `no_price = 100 − yes_price`); handle the symmetry ONE way consistently (Whelan's panel counts Yes and No contracts — document the choice).
2. Bucket by price (1¢ buckets; also 5¢ for stability). Compute empirical win rate per bucket vs. implied probability (price/100).
3. **Confidence intervals must cluster at the event level** (many markets resolve on the same underlying event; outcomes are correlated). Naive binomial CIs will overstate significance. Cluster-bootstrap by `event_ticker` is acceptable.

#### Net-of-fee expected return
4. Apply the current fee schedule per side: taker = 0.07 × P × (1−P) per contract (verify category multipliers — some categories, incl. S&P/Nasdaq series, differ); maker = 25% of taker, 0 on most standard markets, 0.25% flat on designated major events. **Round fees UP to the cent per trade** — at small size the rounding is material.
5. Produce two return curves per bucket: taker-perspective and maker-perspective (using `taker_side` to assign each trade). The strategy question is specifically: **expected return of maker-side purchases at 80–97¢, net of maker fees.**

#### The decay test (the actual deliverable)
6. Split the panel: **pre-2025-09-18** (SSRN publication) vs. **post**. Recompute calibration and net returns for each period. Report whether the favorite-side maker edge is (a) intact, (b) attenuated, (c) gone/negative — with clustered CIs.
7. Segment post-period by category (politics, economics, sports, weather, other) and by liquidity tercile (market total volume). The edge may survive only in some corners.
8. Secondary cut: time-to-expiry buckets (final 24h vs. earlier) — prices are known to sharpen near close; the exploitable window matters.

#### Known pitfalls (encode as tests/assertions)
- **Survivorship/selection:** only settled markets have outcomes — fine — but verify the historical tier isn't silently missing voided/cancelled markets; count and report exclusions.
- **Double counting:** multi-contract mutually exclusive events (e.g., 10 strike buckets on one CPI print) are correlated by construction — this is exactly why clustering matters.
- **Fee drift:** fee schedule changed 2026-02-05; if computing historical net returns, apply the schedule in force at trade time where it materially differs (document if approximated).
- **Category mapping:** series → category mapping comes from /series metadata; snapshot it, don't infer from titles.

### Deliverables
1. `collector/` — resumable backfill CLI (`backfill`, `sync`, `status` subcommands).
2. `analysis/` — reproducible report (notebook or script → markdown/HTML) with: calibration plot, net-return-by-bucket table (maker & taker), pre/post decay comparison with CIs, category & liquidity breakdowns.
3. `VERDICT.md` — one page: does the favorite-side maker edge exist in post-publication data, net of fees? Effect size, CI, capacity note (book-depth observations if phase-2 snapshots ran).

### Go/no-go criteria (pre-committed)
- **GO** if post-publication maker-side net expected return in the 80–97¢ range is positive with clustered 95% CI excluding zero, in at least one liquid category.
- **NO-GO** if the point estimate ≤ 0, or CI spans zero everywhere, or the edge survives only in books too thin to place a $50 order without moving price.
- Either answer is a success — the point is deciding on evidence.

### Explicitly out of scope
- Any order placement, any authenticated endpoint, any live trading logic.
- Longshot-side analysis beyond documentation (strategy never sells/buys longshots).
- Weather-model work (phase 3, separate spec, contingent on GO).

## §2 Verified drift addendum (2026-07-01, live-API probes)

Everything below was verified against `https://api.elections.kalshi.com/trade-api/v2`
with unauthenticated curl on 2026-07-01. Where it contradicts §1, §2 wins.

### 2.1 Cutoff is rolling, not fixed
`GET /historical/cutoff` returns three timestamps, all currently `2026-05-02T00:00:00Z`
(~60 days back): `market_settled_ts`, `orders_updated_ts`, `trades_created_ts`.
The boundary moves; the collector must re-read it every run and treat the
live/historical routing dynamically. Overlap between tiers is handled by
idempotent upserts.

### 2.2 Prices are dollar-strings; fractional trading exists
Trade records do NOT carry integer-cent fields. Observed trade record (exhaustive
key list from live + historical tiers, identical shape):

```
count_fp            "935.19"        -- fractional contract count, string decimal
created_time        RFC3339 timestamp
is_block_trade      bool
no_price_dollars    "0.9900"        -- string decimal, 4dp
taker_book_side     "bid"/"ask"
taker_outcome_side  "yes"/"no"
taker_side          "yes"/"no"      -- the crown jewel, present as promised
ticker              market ticker
trade_id            UUID
yes_price_dollars   "0.0100"
```

Schema change: store prices as DOUBLE dollars (also derived cents for bucketing)
and count as DOUBLE. Prices can be sub-cent-granular in principle
(`fractional_trading_enabled` exists on markets); bucketing logic must bin
non-integer cents rather than assume integers.

### 2.3 Market record shape (settled, both tiers)
Key fields (exhaustive key list captured): `ticker`, `event_ticker`, `title`,
`open_time`, `close_time`, `settlement_ts`, `result`, `status`, `market_type`
(`binary`), `strike_type`, `custom_strike`, `volume_fp`, `volume_24h_fp`,
`open_interest_fp`, `notional_value_dollars`, `liquidity_dollars`,
`last_price_dollars`, `mve_collection_ticker`, `mve_selected_legs`,
`fractional_trading_enabled`, `price_level_structure`, `response_price_units`,
plus bid/ask snapshot fields. **No `category` and no `series_ticker` on the
market record** — category comes via `events` (`event_ticker` → `series_ticker`,
`category`) and `series`. Store normalized `events` and `series` tables and join.

### 2.4 Multivariate (parlay) markets exist and must be excluded from the panel
Markets with non-empty `mve_collection_ticker` (e.g. `KXMVECROSSCATEGORY-…`,
`KXMVESPORTSMULTIGAMEEXTENDED-…`) are auto-generated multi-leg combination
markets. They post-date the paper's sample, their prices are products of leg
prices (mechanically longshot-heavy), and they would contaminate the
calibration panel. Decision: **collect them, exclude from analysis, report the
excluded counts** in the report and VERDICT.md.

### 2.5 Endpoint confirmations
- `GET /historical/markets?limit=1000` — works, no auth, cursor pagination,
  1000/page confirmed, ordered by settlement time **descending** from the cutoff.
- `GET /historical/trades` — works, global firehose (no ticker required),
  `ticker` filter accepted, descending `created_time` from the cutoff.
- `GET /markets?status=settled&min_close_ts=<unix>` — works on the live tier.
- `GET /markets/trades` — works, global descending firehose of live-tier trades.
- `GET /series?limit=…` / `GET /events?limit=…` — work unauthenticated; series
  records carry `category`, `fee_type` (e.g. `"quadratic"`), `fee_multiplier`
  (e.g. `1`); event records carry `event_ticker`, `series_ticker`, `category`,
  `mutually_exclusive`.
- Backfill strategy: **global descending firehose walk** of
  `/historical/trades` and `/historical/markets` until records cross
  2024-01-01, NOT per-ticker fetching (most markets are tiny; per-ticker wastes
  a request minimum per market).

### 2.6 Fee metadata is authoritative in the API
`series.fee_type` + `series.fee_multiplier` ship on every series record. Fee
computation uses these per-series values, not hand-inferred category lists.
The 2026-02-05 schedule change and maker-fee details are captured in §2.7.

### 2.7 Docs-verified details (rate limits, fees, params)
See [`kalshi-api-notes.md`](kalshi-api-notes.md) (written from the
docs-research pass) for: token-bucket numbers for the Basic tier, per-endpoint
query params, 429 behavior, and the current fee schedule table including maker
fees on designated series.

### 2.8 `result` value domain
First 100 settled markets on the live tier: all `result = "no"` (expected —
mutually-exclusive multi-strike events settle mostly-no). Analysis treats
`result ∈ {yes, no}` as the settled universe; anything else (`void`,
empty-string, scalar settlements on non-binary `market_type`) is excluded and
counted in the exclusion report. Only `market_type = "binary"` enters the panel.
