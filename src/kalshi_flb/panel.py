"""Observation panel as lazy DuckDB views.

v_universe: settled binary non-MVE markets in-window, joined to series
metadata (category, fee model). v_obs: every universe trade unpivoted into
its Yes-side and No-side observations (Whelan-style contract counting: both
sides of every trade enter the panel; event-level clustering is the
mitigation for the built-in double counting).

Nothing here materializes: aggregation happens in SQL over ~10^8 rows.
"""
from __future__ import annotations

import shutil
from datetime import timedelta

import pandas as pd

from . import fees


def _next_month(mo):
    return (mo + timedelta(days=32)).replace(day=1)

WINDOW_START = "2024-01-01 00:00:00+00"
PUBLICATION_TS = "2025-09-18 00:00:00+00"

_UNIVERSE_SQL = f"""
CREATE OR REPLACE VIEW v_universe AS
SELECT
  m.ticker, m.event_ticker, m.result, m.close_time, m.settlement_ts,
  m.volume_fp,
  e.series_ticker,
  COALESCE(s.category, 'unknown') AS category,
  COALESCE(e.mutually_exclusive, FALSE) AS mutually_exclusive,
  COALESCE(NULLIF(e.fee_type_override, ''), s.fee_type) AS fee_type,
  COALESCE(e.fee_multiplier_override, s.fee_multiplier, 1.0) AS mult,
  NTILE(3) OVER (ORDER BY COALESCE(m.volume_fp, 0)) AS liq_tercile
FROM markets m
LEFT JOIN events e ON m.event_ticker = e.event_ticker
LEFT JOIN series s ON e.series_ticker = s.series_ticker
WHERE m.market_type = 'binary'
  AND m.result IN ('yes', 'no')
  AND m.settlement_ts >= TIMESTAMPTZ '{WINDOW_START}'
  AND (m.mve_collection_ticker IS NULL OR m.mve_collection_ticker = '')
"""


def _obs_side_sql(side: str, rounding: str | None = None) -> str:
    price = "t.yes_price" if side == "yes" else "t.no_price"
    taker_fee = fees.sql_taker_fee(price, "t.count", "u.mult", "t.created_time",
                                   rounding)
    maker_fee = fees.sql_maker_fee(price, "t.count", "u.mult", "t.created_time",
                                   "u.fee_type", rounding)
    taker_outcome = ("COALESCE(NULLIF(t.taker_outcome_side, ''), "
                     "NULLIF(t.taker_side, ''))")
    # one fee per observation, matching its role — halves the aggregate's
    # spill width vs carrying both roles for every rounding mode
    fee_variants = ",\n  ".join(
        f"CASE WHEN u.fee_type NOT IN ('quadratic', 'quadratic_with_maker_fees') "
        f"THEN 'nan'::DOUBLE "
        f"WHEN {taker_outcome} = '{side}' THEN ({tk}) / t.count "
        f"ELSE ({mk}) / t.count END AS role_fee_pc_{mode}"
        for mode in ("default", "cent", "centicent")
        for tk, mk in [(
            fees.sql_taker_fee(price, "t.count", "u.mult", "t.created_time",
                               None if mode == "default" else mode),
            fees.sql_maker_fee(price, "t.count", "u.mult", "t.created_time",
                               "u.fee_type",
                               None if mode == "default" else mode),
        )])
    return f"""
SELECT
  t.trade_id, t.ticker, u.event_ticker, u.category, u.liq_tercile,
  t.created_time, u.close_time, t.count,
  '{side}' AS side,
  {price} AS price,
  (u.result = '{side}')::INT AS win,
  CASE WHEN COALESCE(NULLIF(t.taker_outcome_side, ''), NULLIF(t.taker_side, '')) IS NULL
       THEN NULL
       ELSE (COALESCE(NULLIF(t.taker_outcome_side, ''), NULLIF(t.taker_side, '')) = '{side}')
  END AS is_taker,
  GREATEST(LEAST(FLOOR(ROUND({price} * 100, 6)), 99), 0)::INT AS bucket_1c,
  GREATEST(LEAST(FLOOR(ROUND({price} * 20, 6)) * 5, 95), 0)::INT AS bucket_5c,
  CASE WHEN t.created_time < TIMESTAMPTZ '{PUBLICATION_TS}'
       THEN 'pre' ELSE 'post' END AS period,
  CASE WHEN u.close_time IS NOT NULL
        AND u.close_time - t.created_time <= INTERVAL 24 HOUR
       THEN 'final24h' ELSE 'earlier' END AS tte_bucket,
  CASE WHEN u.fee_type IN ('quadratic', 'quadratic_with_maker_fees')
       THEN {taker_fee} / t.count ELSE 'nan'::DOUBLE END AS taker_fee_pc,
  CASE WHEN u.fee_type IN ('quadratic', 'quadratic_with_maker_fees')
       THEN {maker_fee} / t.count ELSE 'nan'::DOUBLE END AS maker_fee_pc,
  (u.fee_type IN ('quadratic', 'quadratic_with_maker_fees')) AS fee_ok,
  {fee_variants}
FROM trades t
JOIN v_universe u ON t.ticker = u.ticker
WHERE t.count > 0
"""


def create_views(con, rounding: str | None = None) -> None:
    con.execute(_UNIVERSE_SQL)
    con.execute("CREATE OR REPLACE VIEW v_obs AS "
                + _obs_side_sql("yes", rounding) + " UNION ALL "
                + _obs_side_sql("no", rounding))


AGG_COLS = ("event_ticker, period, category, liq_tercile, tte_bucket, "
            "bucket_1c, is_taker, fee_ok")


def create_agg(con) -> int:
    """Scan the billion-row observation view into an event-level sums table;
    every downstream statistic and bootstrap reads agg_obs instead of
    rescanning v_obs. Fee-rounding variants (default/cent/centicent) land in
    the same pass.

    Processed MONTH BY MONTH: a single scan's out-of-core aggregation spills
    ~1x its input to temp disk, which exceeded free space on the full panel.
    Partial (per-month) rows per group key are fine — every consumer re-SUMs.
    """
    net = ",\n  ".join(
        f"SUM(count * (win - price - role_fee_pc_{mode})) AS net_{mode}"
        for mode in ("default", "cent", "centicent"))
    body = f"""
SELECT
  {AGG_COLS},
  SUM(count)                 AS n,
  SUM(count * win)           AS wins,
  SUM(count * price)         AS price_n,
  SUM(count * (win - price)) AS gross,
  {net}
FROM v_obs
WHERE created_time >= ? AND created_time < ?
GROUP BY ALL"""
    has_trades = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'trades'"
    ).fetchone()[0]
    src = "trades" if has_trades else "v_obs"  # tests fabricate v_obs directly
    months = con.execute(
        f"SELECT date_trunc('month', created_time) AS mo, count(*) "
        f"FROM {src} GROUP BY 1 ORDER BY 1").fetchall()
    # heavy months split into week slices: one slice's out-of-core aggregate
    # spills ~1-2x its input and a 1.7e8-trade month blows the disk budget
    parts = []
    for mo, cnt in months:
        if cnt > 60_000_000:
            starts = [mo + timedelta(days=d) for d in (0, 7, 14, 21, 28)]
            ends = starts[1:] + [_next_month(mo)]
            parts += list(zip(starts, ends))
        else:
            parts.append((mo, _next_month(mo)))
    con.execute(f"""
CREATE OR REPLACE TABLE agg_obs AS
SELECT * FROM ({body}) WHERE 1 = 0""", [parts[0][0], parts[0][0]])
    for lo, hi in parts:
        if shutil.disk_usage(".").free < 12e9:
            raise RuntimeError("aborting agg: <12GB disk free")
        con.execute(f"INSERT INTO agg_obs {body}", [lo, hi])
        con.execute("CHECKPOINT")
        print(f"[agg] {str(lo)[:10]}..{str(hi)[:10]} done", flush=True)
    return con.execute("SELECT count(*) FROM agg_obs").fetchone()[0]


def exclusions(con) -> pd.DataFrame:
    """Everything filtered out of the panel, counted by reason.

    Trade-side counts pre-aggregate per ticker first — anti-joins directly on
    the ~5e8-row trades table OOM; per-ticker groups are ~1e7 rows.
    """
    con.execute("""
CREATE OR REPLACE TEMP TABLE t_by_ticker AS
SELECT ticker,
       count(*) AS n_trades,
       count(*) FILTER (WHERE NULLIF(taker_outcome_side,'') IS NULL
                          AND NULLIF(taker_side,'') IS NULL) AS n_null_taker,
       count(*) FILTER (WHERE count IS NULL OR count <= 0) AS n_nonpos_count,
       count(*) FILTER (WHERE yes_price IS NULL OR no_price IS NULL)
           AS n_null_price
FROM trades GROUP BY ticker""")
    q = f"""
WITH base AS (
  SELECT * FROM markets WHERE settlement_ts IS NOT NULL OR status = 'settled'
)
SELECT 'markets_non_binary' AS reason,
       count(*) AS n FROM base WHERE market_type != 'binary'
UNION ALL
SELECT 'markets_mve', count(*) FROM base
  WHERE market_type = 'binary'
    AND mve_collection_ticker IS NOT NULL AND mve_collection_ticker != ''
UNION ALL
SELECT 'markets_result_void', count(*) FROM base
  WHERE market_type = 'binary' AND result = 'void'
UNION ALL
SELECT 'markets_result_empty', count(*) FROM base
  WHERE market_type = 'binary' AND (result IS NULL OR result = '')
UNION ALL
SELECT 'markets_result_other', count(*) FROM base
  WHERE market_type = 'binary'
    AND result NOT IN ('yes', 'no', 'void', '') AND result IS NOT NULL
UNION ALL
SELECT 'markets_pre_window', count(*) FROM base
  WHERE market_type = 'binary' AND result IN ('yes','no')
    AND settlement_ts < TIMESTAMPTZ '{WINDOW_START}'
UNION ALL
SELECT 'markets_no_series_metadata', count(*) FROM v_universe
  WHERE category = 'unknown'
UNION ALL
SELECT 'markets_flat_fee', count(*) FROM v_universe WHERE fee_type = 'flat'
UNION ALL
SELECT 'trades_mve_by_prefix', coalesce(sum(n_trades), 0) FROM t_by_ticker
  WHERE ticker LIKE 'KXMVE%'
UNION ALL
SELECT 'trades_mve_dropped_at_collection',
       coalesce((SELECT rows_total FROM stream_state
                 WHERE stream = 'trades_mve_dropped'), 0)
UNION ALL
SELECT 'trades_orphaned', coalesce(sum(t.n_trades), 0) FROM t_by_ticker t
  WHERE t.ticker NOT LIKE 'KXMVE%'
    AND NOT EXISTS (SELECT 1 FROM markets m WHERE m.ticker = t.ticker)
UNION ALL
SELECT 'trades_on_excluded_markets', coalesce(sum(t.n_trades), 0)
  FROM t_by_ticker t
  WHERE EXISTS (SELECT 1 FROM markets m WHERE m.ticker = t.ticker)
    AND NOT EXISTS (SELECT 1 FROM v_universe u WHERE u.ticker = t.ticker)
UNION ALL
SELECT 'trades_null_taker', coalesce(sum(t.n_null_taker), 0)
  FROM t_by_ticker t
  WHERE EXISTS (SELECT 1 FROM v_universe u WHERE u.ticker = t.ticker)
UNION ALL
SELECT 'markets_null_volume', count(*) FROM v_universe WHERE volume_fp IS NULL
UNION ALL
SELECT 'trades_nonpositive_count', coalesce(sum(t.n_nonpos_count), 0)
  FROM t_by_ticker t
  WHERE EXISTS (SELECT 1 FROM v_universe u WHERE u.ticker = t.ticker)
UNION ALL
SELECT 'trades_null_price', coalesce(sum(t.n_null_price), 0)
  FROM t_by_ticker t
  WHERE EXISTS (SELECT 1 FROM v_universe u WHERE u.ticker = t.ticker)
"""
    return con.execute(q).df().rename(columns=str.lower)
