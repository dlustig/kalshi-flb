import pytest

from kalshi_flb import db, panel

MK = {
    "market_type": "binary", "status": "settled",
    "open_time": "2025-01-01T00:00:00Z", "close_time": "2026-04-01T00:00:00Z",
    "settlement_ts": "2026-04-01T01:00:00Z", "volume_fp": "100.00",
    "notional_value_dollars": "1.00", "liquidity_dollars": "1.00",
    "open_interest_fp": "0.00", "mve_collection_ticker": "", "strike_type": "",
}
TR = {
    "count_fp": "10.00", "is_block_trade": False, "taker_side": "yes",
    "taker_outcome_side": "yes", "taker_book_side": "bid",
    "created_time": "2026-03-01T00:00:00Z",
}


@pytest.fixture
def panel_con(tmp_path):
    """Small but fully-populated DB with panel views created."""
    c = db.connect(tmp_path / "t.duckdb")
    db.upsert_series(c, [
        {"ticker": "S1", "category": "Economics", "fee_type": "quadratic",
         "fee_multiplier": 1, "title": "s"},
        {"ticker": "SF", "category": "Sports", "fee_type": "flat",
         "fee_multiplier": 1, "title": "s"},
    ])
    db.upsert_events(c, [
        {"event_ticker": "EV1", "series_ticker": "S1", "title": "e",
         "mutually_exclusive": True},
        {"event_ticker": "EVF", "series_ticker": "SF", "title": "e",
         "mutually_exclusive": False},
    ])
    db.upsert_markets(c, [
        dict(MK, ticker="M-YES", event_ticker="EV1", result="yes"),
        dict(MK, ticker="M-NO", event_ticker="EV1", result="no"),
        dict(MK, ticker="M-MVE", event_ticker="EV1", result="yes",
             mve_collection_ticker="KXMVE-XYZ"),
        dict(MK, ticker="M-SCALAR", event_ticker="EV1", result="",
             market_type="scalar"),
        dict(MK, ticker="M-VOID", event_ticker="EV1", result="void"),
        dict(MK, ticker="M-OLD", event_ticker="EV1", result="yes",
             settlement_ts="2023-06-01T00:00:00Z"),
        dict(MK, ticker="M-FLAT", event_ticker="EVF", result="yes"),
    ])
    db.insert_trades(c, [
        # pre-publication trade on M-YES at yes=0.29 (bucket must be 29)
        dict(TR, trade_id="t1", ticker="M-YES", created_time="2025-06-01T00:00:00Z",
             yes_price_dollars="0.2900", no_price_dollars="0.7100"),
        # post-publication trade on M-YES, taker on NO side
        dict(TR, trade_id="t2", ticker="M-YES", yes_price_dollars="0.9000",
             no_price_dollars="0.1000", taker_outcome_side="no", taker_side="no",
             taker_book_side="ask"),
        # trade on MVE market (excluded from panel)
        dict(TR, trade_id="t3", ticker="M-MVE", yes_price_dollars="0.5000",
             no_price_dollars="0.5000"),
        # orphan trade (no market row)
        dict(TR, trade_id="t4", ticker="M-MISSING", yes_price_dollars="0.5000",
             no_price_dollars="0.5000"),
        # null-taker trade on universe market
        dict(TR, trade_id="t5", ticker="M-NO", yes_price_dollars="0.4000",
             no_price_dollars="0.6000", taker_outcome_side="", taker_side=""),
        # trade on flat-fee market (in universe; excluded from net-fee stats)
        dict(TR, trade_id="t6", ticker="M-FLAT", yes_price_dollars="0.8500",
             no_price_dollars="0.1500"),
    ])
    panel.create_views(c)
    return c
