"""Resumable collection streams: Kalshi public API -> DuckDB.

Routing: the rolling /historical/cutoff splits every dataset into a
historical tier (markets settled / trades created before the cutoff) and a
live tier. Each stream persists its cursor in stream_state after every page,
so any run can be killed and rerun; PK-level dedup makes overlap harmless.
"""
from __future__ import annotations

import contextlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

from . import db
from .api import KalshiClient

TRADES_MIN_TS = 1704067200  # 2024-01-01T00:00:00Z — panel window floor
MARKETS_STOP_TS = datetime(2023, 10, 1, tzinfo=UTC)  # early-stop buffer
EARLY_STOP_PAGES = 3  # consecutive all-below-threshold pages before stopping
LIVE_OVERLAP_S = 3600  # re-walk overlap for live trade sync (dedup absorbs it)
LOG_EVERY = 25


class _MarketWalkState(TypedDict):
    monotonic: bool
    below_streak: int
    prev_min: datetime | None


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def get_cutoff(client: KalshiClient) -> dict:
    raw = client.get("/historical/cutoff")
    return {k: _parse_ts(v) for k, v in raw.items()}


_NO_LOCK = contextlib.nullcontext()


def _walk(client, con, stream: str, path: str, list_key: str, params: dict,
          writer, *, limit: int = 1000, watermark_key: str | None = None,
          page_hook=None, max_pages: int | None = None, lock=None) -> int:
    """Generic resumable cursor walk. Returns rows newly written this run.

    `lock` serializes all DB writes when walks run in parallel threads
    (network fetches stay concurrent; duckdb writes go one at a time).
    """
    lock = lock or _NO_LOCK
    with lock:
        st = db.get_stream_state(con, stream)
    if st and st["done"]:
        return 0
    cursor = st["cursor"] if st else None
    total, pages = 0, 0
    for records, next_cursor in client.paginate(path, list_key,
                                                params=params, cursor=cursor,
                                                limit=limit):
        wm = (records[-1].get(watermark_key) or None) \
            if (records and watermark_key) else None
        stop = bool(page_hook and records and page_hook(records))
        done = (not next_cursor) or stop
        with lock:
            n = writer(con, records)
            total += n
            pages += 1
            if not records and next_cursor:
                db.log_progress(con, stream, next_cursor, total, "warn",
                                "empty page with live cursor")
            db.set_stream_state(con, stream, cursor=next_cursor or None,
                                watermark_ts=wm, rows_delta=n, done=done)
            if pages % LOG_EVERY == 0:
                db.log_progress(con, stream, next_cursor, total, "running")
                print(f"[{stream}] pages={pages} rows={total} wm={wm}",
                      file=sys.stderr, flush=True)
        if done:
            break
        if max_pages and pages >= max_pages:
            with lock:
                db.log_progress(con, stream, next_cursor, total, "paused",
                                f"max_pages={max_pages}")
            return total
    with lock:
        db.log_progress(con, stream, None, total, "done")
    return total


def collect_series(client, con) -> int:
    data = client.get("/series")
    recs = data.get("series") or []
    n = db.upsert_series(con, recs)
    db.set_stream_state(con, "series", cursor=None, watermark_ts=None,
                        rows_delta=n, done=True)
    db.log_progress(con, "series", None, n, "done")
    return n


def collect_fee_changes(client, con) -> int:
    """Per-series fee change history (fee-drift accounting in the report)."""
    data = client.get("/series/fee_changes", params={"show_historical": "true"})
    if "series_fee_change_arr" not in data:
        db.log_progress(con, "fee_changes", None, 0, "warn",
                        f"response key missing; got {sorted(data)[:5]}")
        return 0
    recs = data["series_fee_change_arr"] or []
    n = db.upsert_fee_changes(con, recs)
    db.log_progress(con, "fee_changes", None, n, "done")
    return n


def collect_events(client, con, max_pages=None) -> int:
    return _walk(client, con, "events", "/events", "events", {},
                 db.upsert_events, limit=200, watermark_key="last_updated_ts",
                 max_pages=max_pages)


def collect_markets_hist(client, con, max_pages=None) -> int:
    """Walk /historical/markets (observed: settlement-desc order, undocumented).

    Early-stops once EARLY_STOP_PAGES consecutive pages sit entirely below
    MARKETS_STOP_TS — but only while the observed descending order holds.
    Any violation disables early stop and the walk runs to exhaustion.
    """
    state: _MarketWalkState = {"monotonic": True, "below_streak": 0, "prev_min": None}

    def hook(records) -> bool:
        stamps = [_parse_ts(r["settlement_ts"]) for r in records
                  if r.get("settlement_ts")]
        if not stamps:
            return False
        pg_min, pg_max = min(stamps), max(stamps)
        if state["prev_min"] is not None and \
                pg_max > state["prev_min"] + timedelta(days=1):
            if state["monotonic"]:
                state["monotonic"] = False
                db.log_progress(con, "markets_hist", None, 0, "warn",
                                "ordering violation; early-stop disabled")
        state["prev_min"] = min(pg_min, state["prev_min"] or pg_min)
        state["below_streak"] = state["below_streak"] + 1 \
            if pg_max < MARKETS_STOP_TS else 0
        return state["monotonic"] and state["below_streak"] >= EARLY_STOP_PAGES

    # mve_filter=exclude: parlay markets are 80%+ of rows, never enter the
    # panel, and their trades are identifiable by the verified KXMVE ticker
    # prefix (0 mismatches in 1.455M markets) — skipping them at collection
    # cuts the walk ~5x.
    return _walk(client, con, "markets_hist", "/historical/markets", "markets",
                 {"mve_filter": "exclude"}, db.upsert_markets,
                 watermark_key="settlement_ts",
                 page_hook=hook, max_pages=max_pages)


def collect_markets_live(client, con, cutoff, max_pages=None) -> int:
    min_settled = int(cutoff["market_settled_ts"].timestamp()) - 86400
    return _walk(client, con, "markets_live", "/markets", "markets",
                 {"status": "settled", "min_settled_ts": min_settled,
                  "mve_filter": "exclude"},
                 db.upsert_markets, watermark_key="settlement_ts",
                 max_pages=max_pages)


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())


# Disjoint time windows let the trades firehose walk in parallel cursor
# streams (a single cursor is inherently sequential; the API's ~1.4s page
# latency, not our pacing, is the per-cursor floor). Windows are sized by
# observed trade density (recent months run 1-2.5M trades/day); boundaries
# include 2025-09-18 (the publication split) and the old coarse-shard
# watermarks so already-covered ranges never re-walk.
TRADE_SHARD_BOUNDS = [
    "2024-06-01", "2024-10-01", "2024-12-01", "2025-01-22",
    "2025-04-01", "2025-05-01", "2025-06-01", "2025-07-01", "2025-08-01",
    "2025-08-28", "2025-09-18", "2025-10-01", "2025-10-15", "2025-11-01",
    "2025-11-15", "2025-12-01", "2025-12-10", "2025-12-19", "2025-12-28",
    "2026-01-01", "2026-01-08", "2026-01-16", "2026-01-24", "2026-02-01",
    "2026-02-08", "2026-02-15", "2026-02-22", "2026-02-28", "2026-03-01",
    "2026-03-06", "2026-03-11", "2026-03-16", "2026-03-21", "2026-03-26",
    "2026-03-31", "2026-04-05", "2026-04-10", "2026-04-15", "2026-04-20",
    "2026-04-25", "2026-05-01",
]
LIVE_SHARD_BOUNDS = ["2026-05-07", "2026-05-12", "2026-05-17", "2026-05-22",
                     "2026-05-27", "2026-06-01", "2026-06-06", "2026-06-11",
                     "2026-06-16", "2026-06-21", "2026-06-26", "2026-07-01"]
MAX_TRADE_WORKERS = 24
MIN_FREE_DISK_GB = 15


def _shard_name(lo: int, hi: int | None) -> str:
    return f"tr_{lo}_{hi if hi else 'open'}"


def _trade_shards(cutoff) -> list[tuple[str, str, dict]]:
    """Disjoint windows over [TRADES_MIN_TS, now): historical tier up to the
    cutoff, live tier beyond, final live shard open-ended."""
    cut = int(cutoff["trades_created_ts"].timestamp())
    hist = [TRADES_MIN_TS] + [_ts(d) for d in TRADE_SHARD_BOUNDS
                              if _ts(d) < cut] + [cut]
    live = [cut] + [_ts(d) for d in LIVE_SHARD_BOUNDS if _ts(d) > cut]
    shards = [(_shard_name(lo, hi), "/historical/trades",
               {"min_ts": lo, "max_ts": hi})
              for lo, hi in zip(hist, hist[1:])]
    shards += [(_shard_name(lo, hi), "/markets/trades",
                {"min_ts": lo, "max_ts": hi})
               for lo, hi in zip(live, live[1:])]
    shards.append((_shard_name(live[-1], None), "/markets/trades",
                   {"min_ts": live[-1]}))
    return shards


def _free_gb(path=".") -> float:
    import shutil
    return shutil.disk_usage(path).free / 1e9


def _make_trade_writer():
    """Drop parlay trades (KXMVE prefix, verified exact) before insert and
    count the drops in stream_state('trades_mve_dropped')."""
    def writer(con, records):
        keep = [r for r in records if not r["ticker"].startswith("KXMVE")]
        dropped = len(records) - len(keep)
        if dropped:
            db.set_stream_state(con, "trades_mve_dropped", cursor=None,
                                watermark_ts=None, rows_delta=dropped,
                                done=False)
        return db.insert_trades(con, keep)
    return writer


def collect_trades_parallel(con, cutoff, rps: float,
                            max_pages: int | None = None,
                            max_rounds: int = 20) -> int:
    """All trade shards through one shared paced client; a failing shard is
    isolated, logged, and retried next round. Stops when all shards are done,
    a round makes zero progress, or disk drops below the floor."""
    lock = threading.Lock()
    client = KalshiClient(rps=rps)
    writer = _make_trade_writer()
    total = 0

    def run(shard):
        name, path, params = shard
        try:
            return name, _walk(client, con, name, path, "trades", params,
                               writer, watermark_key="created_time",
                               max_pages=max_pages, lock=lock), None
        except Exception as e:  # noqa: BLE001 — shard isolation is the point
            return name, 0, str(e)

    for round_no in range(max_rounds):
        with lock:
            pending = [s for s in _trade_shards(cutoff)
                       if not (st := db.get_stream_state(con, s[0]))
                       or not st["done"]]
        if not pending:
            return total
        # live-tier windows first: the rolling cutoff migrates their data to
        # the historical tier daily, so walk them before it moves underfoot
        pending.sort(key=lambda s: s[1] != "/markets/trades")
        if _free_gb() < MIN_FREE_DISK_GB:
            print(f"[trades] HALT: free disk below {MIN_FREE_DISK_GB}GB",
                  file=sys.stderr, flush=True)
            db.log_progress(con, "trades", None, total, "halted", "low disk")
            return total
        print(f"[trades] round {round_no + 1}: {len(pending)} shards pending",
              file=sys.stderr, flush=True)
        round_rows, failures = 0, []
        with ThreadPoolExecutor(max_workers=MAX_TRADE_WORKERS) as ex:
            for name, rows, err in ex.map(run, pending):
                round_rows += rows
                if err:
                    failures.append((name, err))
                    with lock:
                        db.log_progress(con, name, None, rows, "error", err)
        total += round_rows
        if max_pages:
            return total  # smoke mode: one bounded round only
        if not failures:
            continue  # loop re-checks pending; done shards drop out
        print(f"[trades] round {round_no + 1}: {len(failures)} shard "
              f"failures (will retry): {[f[0] for f in failures][:4]}",
              file=sys.stderr, flush=True)
        if round_rows == 0:
            print("[trades] no progress this round; giving up",
                  file=sys.stderr, flush=True)
            db.log_progress(con, "trades", None, total, "stalled",
                            str(failures[:3]))
            return total
    return total


def _reset(con, streams: list[str]) -> None:
    for s in streams:
        db.set_stream_state(con, s, cursor=None, watermark_ts=None,
                            rows_delta=0, done=False)


def backfill(db_path, rps: float = 8.0, max_pages: int | None = None) -> dict:
    """Run all streams, cheap metadata first, big trade firehose last."""
    client = KalshiClient(rps=rps)
    con = db.connect(db_path)
    cutoff = get_cutoff(client)
    counts = {
        "series": collect_series(client, con),
        "fee_changes": collect_fee_changes(client, con),
        "events": collect_events(client, con, max_pages),
        "markets_hist": collect_markets_hist(client, con, max_pages),
        "markets_live": collect_markets_live(client, con, cutoff, max_pages),
        "trades": collect_trades_parallel(con, cutoff, rps, max_pages),
    }
    con.close()
    return counts


def sync(db_path, rps: float = 8.0) -> dict:
    """Refresh live tier + metadata (historical tier is append-only behind us).

    The open-ended trade shard is reset so it re-walks from 'now' down to its
    floor; bounded shards that are done stay done."""
    client = KalshiClient(rps=rps)
    con = db.connect(db_path)
    cutoff = get_cutoff(client)
    open_shard = _trade_shards(cutoff)[-1][0]
    _reset(con, ["series", "events", "markets_live", open_shard])
    counts = {
        "series": collect_series(client, con),
        "fee_changes": collect_fee_changes(client, con),
        "events": collect_events(client, con),
        "markets_live": collect_markets_live(client, con, cutoff),
        "trades": collect_trades_parallel(con, cutoff, rps),
    }
    con.close()
    return counts


def status(db_path) -> dict:
    con = db.connect(db_path)
    # These aggregate SELECTs have no GROUP BY and always return one row,
    # including on empty tables; fetchone's general annotation also allows None.
    tables = {t: cast(tuple[int], con.execute(f"SELECT count(*) FROM {t}").fetchone())[0]
              for t in ["series", "events", "markets", "trades"]}
    streams = {
        r[0]: {"cursor": bool(r[1]), "watermark": str(r[2]), "rows": r[3],
               "done": r[4], "updated": str(r[5])}
        for r in con.execute(
            "SELECT stream, cursor, watermark_ts, rows_total, done, updated_at "
            "FROM stream_state ORDER BY stream").fetchall()
    }
    span = cast(tuple[datetime | None, datetime | None], con.execute(
        "SELECT min(created_time), max(created_time) FROM trades").fetchone())
    rate = cast(tuple[float | None], con.execute(
        "SELECT sum(rows) / greatest(epoch(max(ts)) - epoch(min(ts)), 1) "
        "FROM (SELECT ts, rows FROM collection_log "
        "      WHERE stream='trades_hist' AND status='running' "
        "      ORDER BY ts DESC LIMIT 10)").fetchone())[0]
    out = {"tables": tables, "streams": streams,
           "trades_span": [str(span[0]), str(span[1])],
           "trades_hist_rows_per_s": float(rate) if rate else None}
    # ETA: descending walk -> remaining span is watermark -> TRADES_MIN_TS
    st = streams.get("trades_hist")
    if st and not st["done"] and st["watermark"] not in (None, "None") and span[0]:
        wm = _parse_ts(st["watermark"].replace(" ", "T")
                       if "T" not in st["watermark"] else st["watermark"])
        covered = (datetime.now(UTC) - wm).total_seconds()
        remaining = (wm - datetime.fromtimestamp(TRADES_MIN_TS, UTC)).total_seconds()
        if covered > 0 and st["rows"]:
            rows_per_span_s = st["rows"] / covered
            est_rows = rows_per_span_s * remaining
            if rate:
                out["trades_hist_eta_hours"] = round(est_rows / rate / 3600, 1)
    con.close()
    return out
