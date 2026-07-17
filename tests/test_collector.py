from datetime import UTC, datetime

import httpx
import pytest

from kalshi_flb import collector, db
from kalshi_flb.api import KalshiClient

CUTOFF_JSON = {
    "market_settled_ts": "2026-05-02T00:00:00Z",
    "orders_updated_ts": "2026-05-02T00:00:00Z",
    "trades_created_ts": "2026-05-02T00:00:00Z",
}


def trade(i, ts="2026-04-30T12:00:00Z"):
    return {
        "trade_id": f"t{i}", "ticker": "MKT-A", "created_time": ts,
        "count_fp": "10.00", "yes_price_dollars": "0.9000",
        "no_price_dollars": "0.1000", "taker_side": "yes",
        "taker_outcome_side": "yes", "taker_book_side": "bid",
        "is_block_trade": False,
    }


def market(ticker, settle_ts):
    return {
        "ticker": ticker, "event_ticker": f"EV-{ticker}", "market_type": "binary",
        "title": ticker, "open_time": "2026-01-01T00:00:00Z",
        "close_time": settle_ts, "settlement_ts": settle_ts, "result": "yes",
        "status": "settled", "volume_fp": "10.00",
        "notional_value_dollars": "1.00", "liquidity_dollars": "1.00",
        "open_interest_fp": "0.00", "mve_collection_ticker": "", "strike_type": "",
    }


def make_client(handler):
    return KalshiClient(transport=httpx.MockTransport(handler), rps=10_000)


@pytest.fixture
def con(tmp_path):
    return db.connect(tmp_path / "t.duckdb")


def test_get_cutoff_parses(con):
    client = make_client(lambda req: httpx.Response(200, json=CUTOFF_JSON))
    c = collector.get_cutoff(client)
    assert c["trades_created_ts"] == datetime(2026, 5, 2, tzinfo=UTC)


def test_collect_series_upserts_and_marks_done(con):
    payload = {"series": [
        {"ticker": "S1", "category": "Economics", "fee_type": "quadratic",
         "fee_multiplier": 1, "title": "s1"},
        {"ticker": "S2", "category": "Sports", "fee_type": "quadratic_with_maker_fees",
         "fee_multiplier": 2, "title": "s2"},
    ]}
    client = make_client(lambda req: httpx.Response(200, json=payload))
    n = collector.collect_series(client, con)
    assert n == 2
    assert con.execute("SELECT count(*) FROM series").fetchone()[0] == 2
    assert db.get_stream_state(con, "series")["done"] is True


def test_collect_events_resumes_from_saved_cursor(con):
    db.set_stream_state(con, "events", cursor="e1", watermark_ts=None,
                        rows_delta=0, done=False)
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json={
            "events": [{"event_ticker": "EV-1", "series_ticker": "S1",
                        "title": "e", "mutually_exclusive": False}],
            "cursor": "",
        })

    client = make_client(handler)
    collector.collect_events(client, con)
    assert seen[0]["cursor"] == "e1"
    assert seen[0]["limit"] == "200"
    assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 1


def test_markets_hist_early_stop_when_monotonic(con):
    # 4 pages, each 1 market, descending settlement; pages 2-4 below stop line
    old = "2023-01-01T00:00:00Z"
    pages = {
        "": {"markets": [market("M1", "2026-01-01T00:00:00Z")], "cursor": "c1"},
        "c1": {"markets": [market("M2", old)], "cursor": "c2"},
        "c2": {"markets": [market("M3", old)], "cursor": "c3"},
        "c3": {"markets": [market("M4", old)], "cursor": "c4"},
        "c4": {"markets": [market("M5", old)], "cursor": "c5"},
        "c5": {"markets": [market("M6", old)], "cursor": ""},
    }
    calls = []

    def handler(req):
        p = dict(req.url.params)
        calls.append(p.get("cursor", ""))
        return httpx.Response(200, json=pages[p.get("cursor", "")])

    client = make_client(handler)
    collector.collect_markets_hist(client, con)
    # early stop after 3 consecutive below-threshold pages: pages "",c1,c2,c3 fetched
    assert len(calls) == 4
    assert db.get_stream_state(con, "markets_hist")["done"] is True


def test_markets_hist_full_walk_on_monotonicity_violation(con):
    old = "2023-01-01T00:00:00Z"
    pages = {
        "": {"markets": [market("M1", old)], "cursor": "c1"},
        "c1": {"markets": [market("M2", "2026-01-01T00:00:00Z")], "cursor": "c2"},  # violation
        "c2": {"markets": [market("M3", old)], "cursor": "c3"},
        "c3": {"markets": [market("M4", old)], "cursor": "c4"},
        "c4": {"markets": [market("M5", old)], "cursor": ""},
    }
    calls = []

    def handler(req):
        p = dict(req.url.params)
        calls.append(p.get("cursor", ""))
        return httpx.Response(200, json=pages[p.get("cursor", "")])

    client = make_client(handler)
    collector.collect_markets_hist(client, con)
    assert len(calls) == 5  # no early stop; walked to exhaustion
    assert con.execute("SELECT count(*) FROM markets").fetchone()[0] == 5


def test_collect_fee_changes(con):
    payload = {"series_fee_change_arr": [
        {"id": "fc1", "series_ticker": "S1", "fee_type": "quadratic",
         "fee_multiplier": 2, "scheduled_ts": "2026-07-03T17:00:00Z"},
    ]}
    client = make_client(lambda req: httpx.Response(200, json=payload))
    n = collector.collect_fee_changes(client, con)
    assert n == 1
    assert con.execute("SELECT count(*) FROM fee_changes").fetchone()[0] == 1
    # idempotent
    collector.collect_fee_changes(client, con)
    assert con.execute("SELECT count(*) FROM fee_changes").fetchone()[0] == 1


def test_trade_shards_contiguous_and_capped():
    cutoff = {"trades_created_ts": datetime(2026, 5, 2, tzinfo=UTC)}
    shards = collector._trade_shards(cutoff)
    hist = [x for x in shards if x[1] == "/historical/trades"]
    live = [x for x in shards if x[1] == "/markets/trades"]
    cut = int(cutoff["trades_created_ts"].timestamp())
    assert hist[0][2]["min_ts"] == collector.TRADES_MIN_TS
    for a, b in zip(hist, hist[1:]):
        assert a[2]["max_ts"] == b[2]["min_ts"]  # disjoint, no gaps
    assert hist[-1][2]["max_ts"] == cut
    assert live[0][2]["min_ts"] == cut
    for a, b in zip(live, live[1:]):
        if "max_ts" in a[2]:
            assert a[2]["max_ts"] == b[2]["min_ts"]
    assert "max_ts" not in live[-1][2]  # open-ended tail shard
    names = [x[0] for x in shards]
    assert len(names) == len(set(names))  # window-derived names are unique


def test_collect_trades_parallel_isolates_failures_and_drops_mve(con):
    cutoff = {"trades_created_ts": datetime(2026, 5, 2, tzinfo=UTC)}
    shards = collector._trade_shards(cutoff)
    fail_min = shards[0][2]["min_ts"]  # first shard fails every time

    def handler(req):
        p = dict(req.url.params)
        if p.get("min_ts") == str(fail_min):
            return httpx.Response(500, text="boom")
        t = trade(f"s{p.get('min_ts', 'open')}")
        t["ticker"] = "KXMVE-PARLAY" if p.get("min_ts", "").endswith("7") \
            else "MKT-A"
        return httpx.Response(200, json={"trades": [t], "cursor": ""})

    real_init = collector.KalshiClient.__init__

    def fake_init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        kw["rps"] = 10_000
        kw["max_retries"] = 2
        real_init(self, *a, **kw)

    collector.KalshiClient.__init__ = fake_init
    try:
        n = collector.collect_trades_parallel(con, cutoff, rps=10_000,
                                              max_rounds=2)
    finally:
        collector.KalshiClient.__init__ = real_init
    # every shard except the failing one landed its (non-MVE) trade
    ok_shards = [x for x in shards if x[2]["min_ts"] != fail_min]
    mve_dropped = collector.db.get_stream_state(con, "trades_mve_dropped")
    stored = con.execute("SELECT count(*) FROM trades").fetchone()[0]
    assert stored + (mve_dropped["rows_total"] if mve_dropped else 0) \
        == len(ok_shards)
    assert n == stored
    # failing shard is not done and logged an error
    assert collector.db.get_stream_state(con, shards[0][0]) is None \
        or not collector.db.get_stream_state(con, shards[0][0])["done"]
    errs = con.execute(
        "SELECT count(*) FROM collection_log WHERE status='error'"
    ).fetchone()[0]
    assert errs >= 1
