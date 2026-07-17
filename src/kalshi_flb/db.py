"""DuckDB storage layer: schema, parsers, idempotent writes, stream state."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS series (
  series_ticker TEXT PRIMARY KEY, category TEXT, title TEXT,
  fee_type TEXT, fee_multiplier DOUBLE, fetched_at TIMESTAMPTZ, raw JSON);
CREATE TABLE IF NOT EXISTS events (
  event_ticker TEXT PRIMARY KEY, series_ticker TEXT, title TEXT,
  mutually_exclusive BOOLEAN, strike_date TIMESTAMPTZ,
  fee_type_override TEXT, fee_multiplier_override DOUBLE, raw JSON);
CREATE TABLE IF NOT EXISTS markets (
  ticker TEXT PRIMARY KEY, event_ticker TEXT, market_type TEXT, title TEXT,
  open_time TIMESTAMPTZ, close_time TIMESTAMPTZ, settlement_ts TIMESTAMPTZ,
  result TEXT, status TEXT, volume_fp DOUBLE, notional_value_dollars DOUBLE,
  liquidity_dollars DOUBLE, open_interest_fp DOUBLE,
  mve_collection_ticker TEXT, strike_type TEXT, raw JSON);
-- No PK on trades: an ART index over ~4e8 UUIDs would exhaust RAM. Shard
-- windows are disjoint so duplicates are confined to bounded overlap slivers;
-- the DQ gate measures them and dedup happens surgically if needed.
CREATE TABLE IF NOT EXISTS trades (
  trade_id TEXT, ticker TEXT, created_time TIMESTAMPTZ,
  yes_price DOUBLE, no_price DOUBLE, count DOUBLE,
  taker_side TEXT, taker_outcome_side TEXT, taker_book_side TEXT,
  is_block_trade BOOLEAN, extra JSON);
CREATE TABLE IF NOT EXISTS fee_changes (
  id TEXT PRIMARY KEY, series_ticker TEXT, fee_type TEXT,
  fee_multiplier DOUBLE, scheduled_ts TIMESTAMPTZ, raw JSON);
CREATE TABLE IF NOT EXISTS stream_state (
  stream TEXT PRIMARY KEY, cursor TEXT, watermark_ts TIMESTAMPTZ,
  rows_total BIGINT DEFAULT 0, done BOOLEAN DEFAULT FALSE,
  updated_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS collection_log (
  ts TIMESTAMPTZ, stream TEXT, cursor TEXT, rows INTEGER,
  status TEXT, note TEXT);
"""

# Closed, verified trade record key set (api-notes 2026-07-01). Anything beyond
# this lands in `extra` so future API additions are never silently dropped.
KNOWN_TRADE_KEYS = {
    "trade_id", "ticker", "created_time", "yes_price_dollars",
    "no_price_dollars", "count_fp", "taker_side", "taker_outcome_side",
    "taker_book_side", "is_block_trade",
}


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    # Bounded memory + disk spill: analysis queries run over ~5e8 rows and an
    # unbounded run has frozen the whole machine (2026-07-02). Conservative
    # limits; heavy steps additionally run under systemd-run MemoryMax so the
    # kernel kills the process, never the box.
    tmp = Path(path).parent / "duckdb_tmp"
    tmp.mkdir(exist_ok=True)
    con.execute("SET memory_limit = '12GB'")
    con.execute("SET threads = 8")
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"SET temp_directory = '{tmp}'")
    con.execute(SCHEMA_SQL)
    return con


def _f(v) -> float | None:
    """Fixed-point decimal string (or number) -> float; ''/None -> None."""
    if v is None or v == "":
        return None
    return float(v)


def parse_trade(rec: dict) -> dict:
    extra = {k: v for k, v in rec.items() if k not in KNOWN_TRADE_KEYS}
    return {
        "trade_id": rec["trade_id"],
        "ticker": rec["ticker"],
        "created_time": rec["created_time"],
        "yes_price": _f(rec.get("yes_price_dollars")),
        "no_price": _f(rec.get("no_price_dollars")),
        "count": _f(rec.get("count_fp")),
        "taker_side": rec.get("taker_side"),
        "taker_outcome_side": rec.get("taker_outcome_side"),
        "taker_book_side": rec.get("taker_book_side"),
        "is_block_trade": rec.get("is_block_trade"),
        "extra": json.dumps(extra, separators=(",", ":")) if extra else None,
    }


def parse_market(rec: dict) -> dict:
    # Multivariate (parlay) markets never enter the analysis panel — only
    # their existence is counted. Dropping their raw JSON (~4KB/row across
    # tens of millions of rows) keeps the DB within disk budget.
    is_mve = bool(rec.get("mve_collection_ticker"))
    return {
        "ticker": rec["ticker"],
        "event_ticker": rec.get("event_ticker"),
        "market_type": rec.get("market_type"),
        "title": rec.get("title"),
        "open_time": rec.get("open_time") or None,
        "close_time": rec.get("close_time") or None,
        "settlement_ts": rec.get("settlement_ts") or None,
        "result": rec.get("result"),
        "status": rec.get("status"),
        "volume_fp": _f(rec.get("volume_fp")),
        "notional_value_dollars": _f(rec.get("notional_value_dollars")),
        "liquidity_dollars": _f(rec.get("liquidity_dollars")),
        "open_interest_fp": _f(rec.get("open_interest_fp")),
        "mve_collection_ticker": rec.get("mve_collection_ticker"),
        "strike_type": rec.get("strike_type"),
        "raw": None if is_mve else json.dumps(rec, separators=(",", ":")),
    }


def parse_event(rec: dict) -> dict:
    return {
        "event_ticker": rec["event_ticker"],
        "series_ticker": rec.get("series_ticker"),
        "title": rec.get("title"),
        "mutually_exclusive": rec.get("mutually_exclusive"),
        "strike_date": rec.get("strike_date") or None,
        "fee_type_override": rec.get("fee_type_override"),
        "fee_multiplier_override": _f(rec.get("fee_multiplier_override")),
        "raw": json.dumps(rec, separators=(",", ":")),
    }


def parse_series(rec: dict) -> dict:
    return {
        "series_ticker": rec["ticker"],
        "category": rec.get("category"),
        "title": rec.get("title"),
        "fee_type": rec.get("fee_type"),
        "fee_multiplier": _f(rec.get("fee_multiplier")),
        "raw": json.dumps(rec, separators=(",", ":")),
    }


_TRADE_COLS = ["trade_id", "ticker", "created_time", "yes_price", "no_price",
               "count", "taker_side", "taker_outcome_side", "taker_book_side",
               "is_block_trade", "extra"]
_MARKET_COLS = ["ticker", "event_ticker", "market_type", "title", "open_time",
                "close_time", "settlement_ts", "result", "status", "volume_fp",
                "notional_value_dollars", "liquidity_dollars",
                "open_interest_fp", "mve_collection_ticker", "strike_type", "raw"]
_EVENT_COLS = ["event_ticker", "series_ticker", "title", "mutually_exclusive",
               "strike_date", "fee_type_override", "fee_multiplier_override", "raw"]
_SERIES_COLS = ["series_ticker", "category", "title", "fee_type",
                "fee_multiplier", "raw"]


def _rows(recs: list[dict], parser, cols: list[str]) -> list[tuple]:
    return [tuple(p[c] for c in cols) for p in (parser(r) for r in recs)]


def _batch_insert(con, table: str, pk: str, cols: list[str],
                  rows: list[tuple], conflict: str) -> int:
    """One vectorized INSERT..SELECT per page. Row-at-a-time executemany was
    ~20x slower and dominated collection wall-clock (network pacing never was
    the bottleneck). Returns rows actually inserted (RETURNING works on a
    single statement, unlike executemany)."""
    import pandas as pd
    df = pd.DataFrame(rows, columns=cols).drop_duplicates(subset=[pk])
    con.register("_batch_df", df)
    try:
        out = con.execute(
            f"INSERT INTO {table} ({','.join(cols)}) "
            f"SELECT * FROM _batch_df {conflict} RETURNING 1").fetchall()
    finally:
        con.unregister("_batch_df")
    return len(out)


def insert_trades(con, recs: list[dict]) -> int:
    if not recs:
        return 0
    import pandas as pd
    df = pd.DataFrame(_rows(recs, parse_trade, _TRADE_COLS),
                      columns=_TRADE_COLS)
    con.register("_batch_df", df)
    try:
        con.execute(f"INSERT INTO trades ({','.join(_TRADE_COLS)}) "
                    "SELECT * FROM _batch_df")
    finally:
        con.unregister("_batch_df")
    return len(df)


def _upsert(con, table: str, pk: str, cols: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0
    setters = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    _batch_insert(con, table, pk, cols, rows,
                  f"ON CONFLICT ({pk}) DO UPDATE SET {setters}")
    return len(rows)


def upsert_markets(con, recs: list[dict]) -> int:
    return _upsert(con, "markets", "ticker", _MARKET_COLS,
                   _rows(recs, parse_market, _MARKET_COLS))


def upsert_fee_changes(con, recs: list[dict]) -> int:
    rows = [(r["id"], r.get("series_ticker"), r.get("fee_type"),
             _f(r.get("fee_multiplier")), r.get("scheduled_ts"),
             json.dumps(r, separators=(",", ":"))) for r in recs]
    return _upsert(con, "fee_changes", "id",
                   ["id", "series_ticker", "fee_type", "fee_multiplier",
                    "scheduled_ts", "raw"], rows)


def upsert_events(con, recs: list[dict]) -> int:
    return _upsert(con, "events", "event_ticker", _EVENT_COLS,
                   _rows(recs, parse_event, _EVENT_COLS))


def upsert_series(con, recs: list[dict]) -> int:
    rows = [t + ("now",) for t in _rows(recs, parse_series, _SERIES_COLS)]
    # fetched_at handled inline to keep one statement
    if not rows:
        return 0
    cols = _SERIES_COLS + ["fetched_at"]
    ph = ",".join("?" * (len(cols) - 1)) + ", now()"
    setters = ",".join(f"{c}=excluded.{c}" for c in cols if c != "series_ticker")
    con.executemany(
        f"INSERT INTO series ({','.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT (series_ticker) DO UPDATE SET {setters}",
        [t[:-1] for t in rows],
    )
    return len(rows)


def get_stream_state(con, stream: str) -> dict | None:
    row = con.execute(
        "SELECT cursor, watermark_ts, rows_total, done FROM stream_state "
        "WHERE stream = ?", [stream]).fetchone()
    if row is None:
        return None
    return {"cursor": row[0], "watermark_ts": row[1],
            "rows_total": row[2], "done": row[3]}


def set_stream_state(con, stream: str, *, cursor, watermark_ts,
                     rows_delta: int, done: bool) -> None:
    prev = get_stream_state(con, stream)
    total = (prev["rows_total"] if prev else 0) + rows_delta
    if watermark_ts is None and prev and not done:
        watermark_ts = prev["watermark_ts"]  # empty page must not erase progress
    con.execute(
        "INSERT OR REPLACE INTO stream_state "
        "(stream, cursor, watermark_ts, rows_total, done, updated_at) "
        "VALUES (?, ?, ?, ?, ?, now())",
        [stream, cursor, watermark_ts, total, done],
    )


def log_progress(con, stream: str, cursor, rows: int, status: str,
                 note: str = "") -> None:
    con.execute(
        "INSERT INTO collection_log VALUES (now(), ?, ?, ?, ?, ?)",
        [stream, cursor, rows, status, note],
    )
