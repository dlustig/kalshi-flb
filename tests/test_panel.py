from kalshi_flb import panel

def test_universe_membership(panel_con):
    tickers = {r[0] for r in panel_con.execute("SELECT ticker FROM v_universe").fetchall()}
    assert tickers == {"M-YES", "M-NO", "M-FLAT"}


def test_obs_two_per_universe_trade(panel_con):
    # universe trades: t1, t2, t5, t6 -> 8 observations
    assert panel_con.execute("SELECT count(*) FROM v_obs").fetchone()[0] == 8


def test_obs_roles_and_wins(panel_con):
    rows = panel_con.execute(
        "SELECT side, price, win, is_taker FROM v_obs WHERE trade_id='t2' "
        "ORDER BY side").fetchall()
    # M-YES settled yes; taker was on the NO side
    assert rows == [("no", 0.10, 0, True), ("yes", 0.90, 1, False)]


def test_bucket_float_noise(panel_con):
    b = panel_con.execute(
        "SELECT bucket_1c, bucket_5c FROM v_obs "
        "WHERE trade_id='t1' AND side='yes'").fetchone()
    assert b == (29, 25)


def test_periods(panel_con):
    rows = dict(panel_con.execute(
        "SELECT trade_id, any_value(period) FROM v_obs GROUP BY 1").fetchall())
    assert rows["t1"] == "pre" and rows["t2"] == "post"


def test_fee_columns(panel_con):
    # quadratic series: maker fee 0; taker fee positive
    r = panel_con.execute(
        "SELECT taker_fee_pc, maker_fee_pc FROM v_obs "
        "WHERE trade_id='t2' AND side='no'").fetchone()
    assert r[0] > 0 and r[1] == 0.0
    # flat series: fees are NaN sentinels
    r = panel_con.execute(
        "SELECT isnan(taker_fee_pc), isnan(maker_fee_pc) FROM v_obs "
        "WHERE trade_id='t6' AND side='yes'").fetchone()
    assert r == (True, True)


def test_null_taker_role_is_null(panel_con):
    r = panel_con.execute(
        "SELECT count(*) FROM v_obs WHERE trade_id='t5' AND is_taker IS NULL"
    ).fetchone()[0]
    assert r == 2


def test_exclusions(panel_con):
    ex = panel.exclusions(panel_con)
    d = dict(zip(ex["reason"], ex["n"]))
    assert d["markets_mve"] == 1
    assert d["markets_non_binary"] == 1
    assert d["markets_result_void"] == 1
    assert d["markets_pre_window"] == 1
    assert d["trades_orphaned"] == 1
    assert d["trades_on_excluded_markets"] == 1  # t3 on M-MVE
    assert d["trades_null_taker"] == 1  # t5
    assert d["markets_flat_fee"] == 1


def test_null_volume_market_not_in_top_tercile(panel_con):
    # NULLS would sort last (=> tercile 3, the verdict gate) without COALESCE
    from kalshi_flb import db
    mk = {
        "ticker": "M-NULLVOL", "event_ticker": "EV1", "market_type": "binary",
        "status": "settled", "result": "yes",
        "open_time": "2025-01-01T00:00:00Z", "close_time": "2026-04-01T00:00:00Z",
        "settlement_ts": "2026-04-01T01:00:00Z", "volume_fp": None,
        "mve_collection_ticker": "", "strike_type": "",
    }
    db.upsert_markets(panel_con, [mk])
    panel.create_views(panel_con)
    t = panel_con.execute(
        "SELECT liq_tercile FROM v_universe WHERE ticker='M-NULLVOL'"
    ).fetchone()[0]
    assert t == 1
    ex = panel.exclusions(panel_con)
    assert dict(zip(ex["reason"], ex["n"]))["markets_null_volume"] == 1
