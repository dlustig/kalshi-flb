import duckdb
import numpy as np
import pytest

from kalshi_flb import calibration

OBS_COLS = ("event_ticker TEXT, bucket_1c INT, bucket_5c INT, price DOUBLE, "
            "win INT, is_taker BOOLEAN, count DOUBLE, period TEXT, "
            "category TEXT, liq_tercile INT, tte_bucket TEXT, "
            "taker_fee_pc DOUBLE, maker_fee_pc DOUBLE, fee_ok BOOLEAN, "
            "created_time TIMESTAMPTZ, role_fee_pc_default DOUBLE, "
            "role_fee_pc_cent DOUBLE, role_fee_pc_centicent DOUBLE")


def make_con(rows):
    from kalshi_flb import panel
    con = duckdb.connect()
    con.execute(f"CREATE TABLE obs ({OBS_COLS})")
    con.executemany(
        "INSERT INTO obs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("CREATE VIEW v_obs AS SELECT * FROM obs")
    panel.create_agg(con)
    return con


def obs(ev, price, win, *, is_taker=False, count=1.0, period="post",
        category="Economics", liq=3, tte="earlier", tfee=0.0, mfee=0.0):
    b1 = int(price * 100)
    b5 = (b1 // 5) * 5
    fee_ok = not (tfee != tfee or mfee != mfee)  # NaN check
    role_fee = tfee if is_taker else mfee
    return (ev, b1, b5, price, win, is_taker, count, period, category, liq,
            tte, tfee, mfee, fee_ok, "2026-03-01T00:00:00Z",
            role_fee, role_fee, role_fee)


def test_known_answer_win_rate():
    rows = []
    for ev, wins in [("E1", 9), ("E2", 9), ("E3", 8), ("E4", 10)]:
        rows += [obs(ev, 0.90, 1) for _ in range(wins)]
        rows += [obs(ev, 0.90, 0) for _ in range(10 - wins)]
    con = make_con(rows)
    sums = calibration.event_sums(con, bucket_col="bucket_5c", role="maker")
    stats = calibration.bucket_stats(sums)
    assert len(stats) == 1
    r = stats.iloc[0]
    assert r["bucket"] == 90
    assert r["n"] == 40
    assert r["win_rate"] == pytest.approx(0.9)
    assert r["mean_price"] == pytest.approx(0.9)
    assert r["ev_gross_pc"] == pytest.approx(0.0)
    assert r["ev_net_pc"] == pytest.approx(0.0)


def test_bootstrap_contains_truth_and_deterministic():
    rows = []
    for ev, wins in [("E1", 9), ("E2", 9), ("E3", 8), ("E4", 10)]:
        rows += [obs(ev, 0.90, 1) for _ in range(wins)]
        rows += [obs(ev, 0.90, 0) for _ in range(10 - wins)]
    con = make_con(rows)
    sums = calibration.event_sums(con, bucket_col="bucket_5c", role="maker")
    lo1, hi1 = calibration.cluster_bootstrap(sums, "wins", "n", seed=1)
    lo2, hi2 = calibration.cluster_bootstrap(sums, "wins", "n", seed=1)
    assert (lo1, hi1) == (lo2, hi2)
    assert lo1 <= 0.9 <= hi1
    assert 0.75 <= lo1 < hi1 <= 1.0


def test_bootstrap_single_event_is_nan():
    con = make_con([obs("E1", 0.90, 1)])
    sums = calibration.event_sums(con, bucket_col="bucket_5c", role="maker")
    lo, hi = calibration.cluster_bootstrap(sums, "wins", "n")
    assert np.isnan(lo) and np.isnan(hi)


def test_calibrated_synthetic_within_ci():
    rng = np.random.default_rng(7)
    rows = []
    for i in range(400):
        p = rng.choice([0.82, 0.87, 0.92])
        for _ in range(10):
            rows.append(obs(f"E{i}", p, int(rng.random() < p)))
    con = make_con(rows)
    sums = calibration.event_sums(con, bucket_col="bucket_5c", role="maker")
    stats = calibration.bucket_stats(sums)
    for _, r in stats.iterrows():
        sub = sums[sums["bucket"] == r["bucket"]]
        lo, hi = calibration.cluster_bootstrap(sub, "wins", "n", seed=2)
        assert lo <= r["mean_price"] <= hi, f"bucket {r['bucket']} miscalibrated"


def test_biased_synthetic_headline_positive():
    rng = np.random.default_rng(11)
    rows = []
    for i in range(600):
        p = float(rng.choice([0.85, 0.90, 0.95]))
        for _ in range(10):
            # favorites win 4 points more often than priced
            rows.append(obs(f"E{i}", p, int(rng.random() < min(p + 0.04, 1.0))))
    con = make_con(rows)
    h = calibration.headline(con)
    post = h["post"]["overall"]
    assert post["ev_net_pc"] > 0
    assert post["ci_lo"] > 0
    assert post["n_events"] == 600
    assert "by_category" in h["post"] and "by_liq_tercile" in h["post"]


def test_roles_split():
    rows = [obs("E1", 0.9, 1, is_taker=True), obs("E1", 0.9, 1, is_taker=False),
            obs("E1", 0.1, 0, is_taker=None)]
    con = make_con(rows)
    maker = calibration.event_sums(con, bucket_col="bucket_5c", role="maker")
    taker = calibration.event_sums(con, bucket_col="bucket_5c", role="taker")
    assert maker["n"].sum() == 1 and taker["n"].sum() == 1


def test_nan_fee_rows_excluded():
    rows = [obs("E1", 0.9, 1, mfee=float("nan")), obs("E2", 0.9, 1, mfee=0.001)]
    con = make_con(rows)
    sums = calibration.event_sums(con, bucket_col="bucket_5c", role="maker")
    assert sums["n"].sum() == 1
