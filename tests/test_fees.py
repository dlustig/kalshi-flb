import math
from datetime import UTC, datetime

import duckdb
import numpy as np
import pytest

from kalshi_flb import fees

PRE = datetime(2025, 6, 1, tzinfo=UTC)   # cent-rounding era
POST = datetime(2026, 6, 1, tzinfo=UTC)  # centicent era


def test_taker_fee_midpoint():
    # 0.07 * 0.5 * 0.5 = 0.0175 exactly
    assert fees.taker_fee(0.50, 1, 1, POST) == pytest.approx(0.0175)
    assert fees.taker_fee(0.50, 1, 1, PRE) == pytest.approx(0.02)


def test_taker_fee_favorite():
    # 0.07 * 0.95 * 0.05 = 0.003325 -> ceil to 0.0034 (post) / 0.01 (pre)
    assert fees.taker_fee(0.95, 1, 1, POST) == pytest.approx(0.0034)
    assert fees.taker_fee(0.95, 1, 1, PRE) == pytest.approx(0.01)


def test_taker_fee_exact_multiple_no_extra_roundup():
    # 0.07 * 100 * 0.95 * 0.05 = 0.3325 exactly -> stays 0.3325
    assert fees.taker_fee(0.95, 100, 1, POST) == pytest.approx(0.3325)


def test_multiplier_scales_before_rounding():
    assert fees.taker_fee(0.95, 1, 2, POST) == pytest.approx(0.0067)  # 0.00665 -> 0.0067


def test_maker_fee_types():
    assert fees.maker_fee(0.95, 100, 1, "quadratic", POST) == 0.0
    # 0.25 * 0.3325 = 0.083125 -> 0.0832
    assert fees.maker_fee(0.95, 100, 1, "quadratic_with_maker_fees", POST) == pytest.approx(0.0832)
    assert math.isnan(fees.maker_fee(0.95, 100, 1, "flat", POST))


def test_sql_parity_with_python():
    rng = np.random.default_rng(42)
    n = 500
    prices = np.round(rng.uniform(0.01, 0.99, n), 4)
    counts = np.round(rng.uniform(0.01, 500, n), 2)
    mults = rng.choice([1.0, 2.0], n)
    eras = rng.choice([PRE, POST], n)

    con = duckdb.connect()
    con.execute("CREATE TABLE t (price DOUBLE, cnt DOUBLE, mult DOUBLE, ts TIMESTAMPTZ)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?, ?)",
                    list(zip(prices, counts, mults, eras)))
    got = con.execute(
        f"SELECT {fees.sql_taker_fee('price', 'cnt', 'mult', 'ts')} FROM t"
    ).fetchnumpy()
    sql_vals = next(iter(got.values()))
    py_vals = [fees.taker_fee(p, c, m, e)
               for p, c, m, e in zip(prices, counts, mults, eras)]
    np.testing.assert_allclose(sql_vals, py_vals, atol=1e-9)


def test_sql_maker_parity_with_python():
    con = duckdb.connect()
    con.execute("CREATE TABLE t (price DOUBLE, cnt DOUBLE, mult DOUBLE, ts TIMESTAMPTZ, fee_type TEXT)")
    rows = [(0.95, 100.0, 1.0, POST, "quadratic"),
            (0.95, 100.0, 1.0, POST, "quadratic_with_maker_fees"),
            (0.85, 3.5, 1.0, PRE, "quadratic_with_maker_fees")]
    con.executemany("INSERT INTO t VALUES (?, ?, ?, ?, ?)", rows)
    got = con.execute(
        f"SELECT {fees.sql_maker_fee('price', 'cnt', 'mult', 'ts', 'fee_type')} FROM t"
    ).fetchall()
    py = [fees.maker_fee(r[0], r[1], r[2], r[4], r[3]) for r in rows]
    assert got[0][0] == 0.0 and py[0] == 0.0
    assert got[1][0] == pytest.approx(py[1])
    assert got[2][0] == pytest.approx(py[2])
