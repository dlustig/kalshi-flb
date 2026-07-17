# Kalshi API — verified reference (2026-07-01)

Sources: docs.kalshi.com (api-reference/historical/*, api-reference/market/*,
getting_started/{historical_data,rate_limits,fee_rounding}, changelog) plus
direct unauthenticated probes of `https://api.elections.kalshi.com/trade-api/v2`.
Where docs and probes agree, entries are marked ✅. Anything inferred from
probes only is marked (observed).

## Base URL
`https://api.elections.kalshi.com/trade-api/v2` ✅ (docs now also list
`external-api.kalshi.com/trade-api/v2`; either works, no separate historical host).
No auth required for any endpoint below.

## Endpoints

### GET /historical/cutoff ✅
No params. Response: `{market_settled_ts, trades_created_ts, orders_updated_ts}`
(RFC3339 strings). Currently all `2026-05-02T00:00:00Z` — a rolling ~60-day
boundary, NOT fixed. Markets settled before `market_settled_ts` live in
`/historical/markets`; trades created before `trades_created_ts` live in
`/historical/trades`. Re-read every collector run.

### GET /historical/markets ✅
Params: `limit` (default 100, max 1000 — confirmed live), `cursor`, `tickers`
(comma-sep), `event_ticker`, `series_ticker`, `mve_filter=exclude`.
Filters are mutually exclusive. **No status/time-range params.**
(observed) Unfiltered walk returns settled markets ordered by settlement time
descending from the cutoff. Ordering is NOT documented — any early-stop
heuristic must assert monotonicity and fall back to a full walk.
Response: `{markets: [...], cursor}`; empty cursor = last page.

### GET /historical/trades ✅
Params: `ticker`, `min_ts` (unix int), `max_ts` (unix int), `limit` (default
100, max 1000), `cursor`, `is_block_trade`. Global firehose works (no ticker
required). Time filters confirmed live: min_ts/max_ts at 2024-01-01 returned
2024-01-01 trades, descending from max_ts. Data exists back to ≥2024-01-01.

### GET /markets (live tier) ✅
Params: `limit` (≤1000), `cursor`, `status` (`unopened|open|paused|closed|settled`),
`tickers`, `event_ticker`, `series_ticker` (requires `mve_filter=exclude`),
`min_created_ts`/`max_created_ts`, `min_close_ts`/`max_close_ts`,
`min_settled_ts`/`max_settled_ts`, `min_updated_ts`, `mve_filter` (`only|exclude`).
Live tier only retains post-cutoff data (~last 60 days of settled markets).

### GET /markets/trades (live tier) ✅
Params: `ticker`, `min_ts`, `max_ts`, `limit` (≤1000), `cursor`,
`is_block_trade`. Same record shape as historical. Descending created_time.

### GET /series ✅
Params: `category` (OPTIONAL), `tags`, `include_product_metadata`,
`include_volume`, `min_updated_ts`. **No pagination** — returns all series in
one response (`{series: [...]}`, 11,135 records on 2026-07-01, ~a few MB).
Series record: `ticker`, `title`, `category`, `frequency`, `tags`,
`fee_type` (`quadratic` | `quadratic_with_maker_fees` | `flat`),
`fee_multiplier` (number), `settlement_sources`, `contract_url`, etc.
THIS is the authoritative category and fee mapping.

### GET /events ✅
Params: `limit` (default 200, **max 200** — not 1000), `cursor`, `status`,
`series_ticker`, `tickers`, `with_nested_markets`, `min_close_ts`,
`min_updated_ts`. Event record: `event_ticker`, `series_ticker`, `title`,
`sub_title`, `mutually_exclusive` (bool), `strike_date`, `strike_period`,
`category` (**deprecated** — use series.category), `fee_type_override`,
`fee_multiplier_override`, `collateral_return_type`, `last_updated_ts`.

## Record shapes (fixed-point-string era, post Jan–Mar 2026 migration)

### Trade (identical live + historical; exhaustive key list, probed) ✅
```
trade_id            UUID string
ticker              market ticker
created_time        RFC3339 (µs precision)
count_fp            string decimal, 2dp   -- fractional contracts ("935.19")
yes_price_dollars   string decimal (docs: up to 6dp; observed 4dp)
no_price_dollars    string decimal
taker_side          "yes"/"no"  -- DEPRECATED 2026-05-06; removal "not before 2026-05-14"
taker_outcome_side  "yes"/"no"  -- replacement; use this
taker_book_side     "bid"/"ask" -- bid = yes-side taker, ask = no-side taker
is_block_trade      bool
```
Integer-cent `yes_price`/`no_price`/`count` fields are GONE.

### Market (settled; exhaustive key list, probed) ✅
`ticker, event_ticker, market_type(binary|scalar), title(deprecated),
yes_sub_title, no_sub_title, created_time, updated_time, open_time, close_time,
latest_expiration_time, expected_expiration_time, status, result(yes|no|scalar|""),
settlement_ts, settlement_value_dollars, settlement_timer_seconds,
yes_bid_dollars, yes_ask_dollars, no_bid_dollars, no_ask_dollars,
last_price_dollars, previous_*, volume_fp, volume_24h_fp, open_interest_fp,
notional_value_dollars, liquidity_dollars, rules_primary, rules_secondary,
can_close_early, custom_strike, strike_type, price_level_structure,
price_ranges, response_price_units, mve_collection_ticker, mve_selected_legs,
fractional_trading_enabled, expiration_value`
No `category`, no `series_ticker` — join via events → series.
Non-empty `mve_collection_ticker` ⇒ multivariate (parlay) market.

## Rate limits ✅
Token bucket, separate Read/Write. Default cost **10 tokens/request**.
Basic tier: Read refills **200 tokens/sec ≈ 20 req/s**; bucket capacity ≈ 1s
of budget. 429 body `{"error":"too many requests"}` with **no Retry-After and
no X-RateLimit-* headers** (explicitly documented). Docs describe tiers per
account/API key; unauthenticated bucketing (per-IP?) unspecified — be polite.

## Fees
- Rounding: **up to the nearest $0.0001** (centicent) per the current
  fee_rounding doc. The round-up-to-cent rule is the pre-migration era.
- Per-series `fee_type` + `fee_multiplier`; per-event overrides
  (`fee_type_override`, `fee_multiplier_override`).
- Coefficients (taker 0.07·C·P·(1−P); maker 25% of taker on
  `quadratic_with_maker_fees` series) — **unconfirmed against the official
  PDF** (`kalshi.com/docs/kalshi-fee-schedule.pdf`, titled "Fee Schedule for
  June 2026", returned 429 on 2026-07-01). Re-verify during execution.
- API changelog shows NO fee change on 2026-02-05 (that entry is an
  incentive-programs field). The brief's 2026-02-05 fee-change date is
  unconfirmed; treat rounding-era boundary as approximate + sensitivity-test.
- `flat` fee_type semantics undocumented in API docs — resolve from the PDF or
  exclude flat-fee series from fee-sensitive results (count them).
- PDF fetch attempts: 2026-07-01 (curl, docs-researcher) and 2026-07-02 (curl
  with browser UA, WebFetch x2) — all 429 (Cloudflare). help.kalshi.com/trading/fees
  (fetched 2026-07-02) confirms fee *structure* (maker fee = resting orders,
  charged only on execution; "some markets have fees that are different":
  special events/elections/championships) but carries no formulas. Coefficients
  remain brief-sourced + third-party cross-checked; report caveat stands.

## Environment facts (this machine, 2026-07-01)
- Network: NOT air-gapped; API reachable.
- Disk: 124 GB free on the target volume.
- Python 3.10 system; uv with CPython 3.12.13 and 3.14.4 installed.
