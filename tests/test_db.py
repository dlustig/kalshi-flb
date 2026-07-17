import json

import pytest

from kalshi_flb import db

# Verbatim record shapes from live probes 2026-07-01 (see api-notes spec).
TRADE_REC = {
    "count_fp": "935.19",
    "created_time": "2026-07-01T22:00:00.429839Z",
    "is_block_trade": False,
    "no_price_dollars": "0.9900",
    "taker_book_side": "bid",
    "taker_outcome_side": "yes",
    "taker_side": "yes",
    "ticker": "KXWCGAME-26JUL01BELSEN-SEN",
    "trade_id": "31986fdf-a413-4740-d2fc-8bd98c1d7da6",
    "yes_price_dollars": "0.0100",
}

MARKET_REC = {
    "ticker": "KXTEST-26JUL01-A",
    "event_ticker": "KXTEST-26JUL01",
    "market_type": "binary",
    "title": "Test market",
    "open_time": "2026-06-01T00:00:00Z",
    "close_time": "2026-07-01T00:00:00Z",
    "settlement_ts": "2026-07-01T01:00:00Z",
    "result": "yes",
    "status": "settled",
    "volume_fp": "1234.00",
    "notional_value_dollars": "1.00",
    "liquidity_dollars": "50.0000",
    "open_interest_fp": "10.00",
    "mve_collection_ticker": "",
    "strike_type": "greater",
    "can_close_early": True,
}

EVENT_REC = {
    "event_ticker": "KXTEST-26JUL01",
    "series_ticker": "KXTEST",
    "title": "Test event",
    "mutually_exclusive": True,
    "strike_date": "2026-07-01T00:00:00Z",
}

SERIES_REC = {
    "ticker": "KXTEST",
    "category": "Economics",
    "title": "Test series",
    "fee_type": "quadratic",
    "fee_multiplier": 1,
}


@pytest.fixture
def con(tmp_path):
    return db.connect(tmp_path / "t.duckdb")


def test_schema_idempotent(tmp_path):
    p = tmp_path / "t.duckdb"
    c1 = db.connect(p)
    c1.close()
    c2 = db.connect(p)  # second connect must not fail on existing tables
    assert c2.execute("SELECT count(*) FROM trades").fetchone()[0] == 0


def test_parse_trade_types():
    t = db.parse_trade(TRADE_REC)
    assert t["yes_price"] == 0.01
    assert t["no_price"] == 0.99
    assert t["count"] == 935.19
    assert t["taker_outcome_side"] == "yes"
    assert t["taker_book_side"] == "bid"
    assert t["taker_side"] == "yes"
    assert t["extra"] is None


def test_parse_trade_unknown_keys_go_to_extra():
    rec = dict(TRADE_REC, mystery_field="hello")
    t = db.parse_trade(rec)
    assert json.loads(t["extra"]) == {"mystery_field": "hello"}


def test_insert_trades_appends(con):
    # no PK by design (ART index over ~4e8 UUIDs would exhaust RAM);
    # dedup is measured at the DQ gate instead of enforced per-insert
    assert db.insert_trades(con, [TRADE_REC]) == 1
    assert db.insert_trades(con, [TRADE_REC]) == 1
    assert con.execute("SELECT count(*) FROM trades").fetchone()[0] == 2


def test_upsert_market_twice_updates(con):
    db.upsert_markets(con, [MARKET_REC])
    changed = dict(MARKET_REC, result="no")
    db.upsert_markets(con, [changed])
    rows = con.execute("SELECT result, count(*) FROM markets GROUP BY 1").fetchall()
    assert rows == [("no", 1)]


def test_upsert_event_and_series(con):
    db.upsert_events(con, [EVENT_REC])
    db.upsert_series(con, [SERIES_REC])
    row = con.execute(
        "SELECT e.series_ticker, s.category, s.fee_type FROM events e "
        "JOIN series s ON s.series_ticker = e.series_ticker"
    ).fetchone()
    assert row == ("KXTEST", "Economics", "quadratic")


def test_stream_state_roundtrip(con):
    assert db.get_stream_state(con, "trades_hist") is None
    db.set_stream_state(con, "trades_hist", cursor="abc",
                        watermark_ts="2026-05-01T00:00:00Z", rows_delta=1000, done=False)
    st = db.get_stream_state(con, "trades_hist")
    assert st["cursor"] == "abc"
    assert st["rows_total"] == 1000
    assert st["done"] is False
    db.set_stream_state(con, "trades_hist", cursor=None,
                        watermark_ts=None, rows_delta=500, done=True)
    st = db.get_stream_state(con, "trades_hist")
    assert st["rows_total"] == 1500
    assert st["done"] is True


def test_parse_market_mve_drops_raw():
    mve = dict(MARKET_REC, mve_collection_ticker="KXMVE-XYZ")
    assert db.parse_market(mve)["raw"] is None
    assert db.parse_market(MARKET_REC)["raw"] is not None
