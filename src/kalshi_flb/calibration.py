"""Calibration statistics with event-clustered bootstrap CIs.

All aggregation runs in DuckDB over the lazy v_obs view; Python only ever
sees per-event sums (≤ a few hundred thousand rows), never raw observations.
CIs are percentile bootstrap over event resampling — events are the cluster
unit because multi-strike events and Yes/No symmetry correlate outcomes
within an event by construction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAKER_RANGE = (0.80, 0.97)  # the strategy's favorite-side window
N_BOOT = 1000

_ROLES = {
    "maker": "is_taker = FALSE AND fee_ok",
    "taker": "is_taker = TRUE AND fee_ok",
    "all": "TRUE",
}


def event_sums(con, *, bucket_col: str | None, role: str,
               group_cols: tuple[str, ...] = (), where: str = "",
               mode: str = "default") -> pd.DataFrame:
    """Per-(event, bucket, *group_cols) weighted sums from the materialized
    agg_obs table (built by panel.create_agg — one scan of the raw panel).

    `mode` picks the fee-rounding variant for `net` ('default' era-based,
    'cent', 'centicent'). Role 'all' has no fee meaning: net = gross.
    `where`/`bucket_col` reference agg_obs columns; prices are pre-summed, so
    price-range filters use bucket_1c (e.g. "bucket_1c BETWEEN 80 AND 96").
    """
    role_filter = _ROLES[role]
    net_col = "gross" if role == "all" else f"net_{mode}"
    if bucket_col == "bucket_5c":
        bucket_col = "(bucket_1c // 5) * 5"  # derived; agg stores 1c only
    bucket_expr = bucket_col if bucket_col else "'all'"
    groups = "".join(f", {g}" for g in group_cols)
    q = f"""
SELECT event_ticker, {bucket_expr} AS bucket{groups},
  SUM(n)         AS n,
  SUM(wins)      AS wins,
  SUM(price_n)   AS price_n,
  SUM(gross)     AS gross,
  SUM({net_col}) AS net
FROM agg_obs
WHERE {role_filter} {f'AND ({where})' if where else ''}
GROUP BY ALL
"""
    return con.execute(q).df()


def bucket_stats(sums: pd.DataFrame,
                 group_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    keys = ["bucket", *group_cols]
    g = sums.groupby(keys, as_index=False).agg(
        n=("n", "sum"), wins=("wins", "sum"), price_n=("price_n", "sum"),
        gross=("gross", "sum"), net=("net", "sum"),
        n_events=("event_ticker", "nunique"))
    g["win_rate"] = g["wins"] / g["n"]
    g["mean_price"] = g["price_n"] / g["n"]
    g["ev_gross_pc"] = g["gross"] / g["n"]
    g["ev_net_pc"] = g["net"] / g["n"]
    g["ev_net_pct"] = g["net"] / g["price_n"]
    return g


def cluster_bootstrap(sums: pd.DataFrame, num_col: str, den_col: str,
                      n_boot: int = N_BOOT, seed: int = 20260701,
                      chunk: int = 200) -> tuple[float, float]:
    """95% percentile CI for sum(num)/sum(den), resampling events."""
    ev = sums.groupby("event_ticker").agg({num_col: "sum", den_col: "sum"})
    num = ev[num_col].to_numpy(float)
    den = ev[den_col].to_numpy(float)
    n_events = len(ev)
    if n_events < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    # bound weight-matrix memory to ~20M cells regardless of event count
    chunk = max(1, min(chunk, int(2e7 / max(n_events, 1))))
    p = np.full(n_events, 1.0 / n_events)
    done = 0
    while done < n_boot:
        b = min(chunk, n_boot - done)
        w = rng.multinomial(n_events, p, size=b).astype(np.float32)
        stats[done:done + b] = (w @ num) / (w @ den)
        done += b
    return (float(np.nanpercentile(stats, 2.5)),
            float(np.nanpercentile(stats, 97.5)))


def stat_block(sums: pd.DataFrame) -> dict:
    if sums.empty or sums["n"].sum() == 0:
        return {"n": 0.0, "n_events": 0, "win_rate": None, "mean_price": None,
                "ev_net_pc": None, "ev_net_pct": None,
                "ci_lo": None, "ci_hi": None}
    s = bucket_stats(sums).iloc[0]
    lo, hi = cluster_bootstrap(sums, "net", "n")
    return {"n": float(s["n"]), "n_events": int(s["n_events"]),
            "win_rate": float(s["win_rate"]),
            "mean_price": float(s["mean_price"]),
            "ev_net_pc": float(s["ev_net_pc"]),
            "ev_net_pct": float(s["ev_net_pct"]),
            "ci_lo": lo, "ci_hi": hi}


MAKER_WHERE = "bucket_1c BETWEEN 80 AND 96"  # price ∈ [0.80, 0.97)


def headline(con, mode: str = "default") -> dict:
    """The deliverable stat: maker-side net EV at 80-97¢, pre vs post, segmented."""
    out = {}
    for period in ("pre", "post"):
        w = f"{MAKER_WHERE} AND period = '{period}'"
        block = {"overall": stat_block(
            event_sums(con, bucket_col=None, role="maker", where=w, mode=mode))}
        for key, col, extra in (("by_category", "category", ""),
                                ("by_liq_tercile", "liq_tercile", ""),
                                ("by_tte", "tte_bucket", ""),
                                ("by_category_liquid", "category",
                                 " AND liq_tercile = 3")):
            sums = event_sums(con, bucket_col=None, role="maker",
                              group_cols=(col,), where=w + extra, mode=mode)
            block[key] = {
                str(val): stat_block(sub.drop(columns=[col]))
                for val, sub in sums.groupby(col)}
        out[period] = block
    return out
