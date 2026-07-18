"""Generate the interactive dashboard's data file from the analysis DB.

Reads the already-materialized `agg_obs` table (event x bucket x segment sums)
and reuses the tested calibration code to emit `web/data/stats.json` — the single
data source for the GitHub Pages dashboard. Reading agg_obs is cheap and
low-memory; this does NOT rebuild the panel (that is the expensive, machine-
caged step). Safe to run any time after a `kalshi-flb report`.

Usage:  uv run python scripts/build_site_data.py [db_path] [out_path]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from kalshi_flb import calibration, db

# 5c buckets 0..95; the dashboard plots these on a cents x-axis.
ROLES = ("all", "maker", "taker")
PERIODS = ("pre", "post")


def _round(x, n):
    return None if x is None or x != x else round(float(x), n)


def _curve_row(stats_row) -> dict:
    """One bucket's point estimates, in display units (cents / percent)."""
    return {
        "bucket": int(stats_row["bucket"]),
        "price_c": _round(stats_row["mean_price"] * 100, 2),
        "win_pct": _round(stats_row["win_rate"] * 100, 2),
        "net_c": _round(stats_row["ev_net_pc"] * 100, 3),
        "n": int(stats_row["n"]),
    }


CI_BOOT = 400  # CI bands are illustrative; 400 replicates is plenty and ~2.5x faster


def _pooled_ci(sums, metrics) -> dict[int, dict]:
    """Per-bucket clustered 95% CIs for the pooled (all-category) series. Only
    the pooled series carries bands; per-category curves show point lines (their
    headline CIs live in the bar chart). `metrics` is a subset of {win, net} —
    we bootstrap only the band the dashboard actually draws for this role
    (win rate for the calibration overlay, net EV for the maker/taker overlay)."""
    out = {}
    for b in sorted(sums["bucket"].unique()):
        sub = sums[sums["bucket"] == b]
        row = {}
        if "win" in metrics:
            lo, hi = calibration.cluster_bootstrap(sub, "wins", "n", n_boot=CI_BOOT)
            row["win_lo"], row["win_hi"] = _round(lo * 100, 2), _round(hi * 100, 2)
        if "net" in metrics:
            lo, hi = calibration.cluster_bootstrap(sub, "net", "n", n_boot=CI_BOOT)
            row["net_lo"], row["net_hi"] = _round(lo * 100, 3), _round(hi * 100, 3)
        out[int(b)] = row
    return out


def build_curves(con) -> dict:
    """curves["<period>|<role>|<category>"] -> per-bucket point estimates.

    One agg_obs scan per (period, role); categories are sliced in memory. The
    synthetic 'All' category is the pooled series and is the only one given CI
    bands (win rate + net EV)."""
    curves = {}
    for period in PERIODS:
        for role in ROLES:
            print(f"[curves] {period}/{role}: scanning agg_obs ...", flush=True)
            sums = calibration.event_sums(
                con, bucket_col="bucket_5c", role=role,
                group_cols=("category",), where=f"period = '{period}'")
            if sums.empty:
                continue

            # pooled ("All") series, with the CI band the dashboard draws for
            # this role: win-rate band on the calibration ('all') overlay,
            # net-EV band on the maker/taker overlay.
            pooled = calibration.bucket_stats(sums).sort_values("bucket")
            ci = _pooled_ci(sums, ("win",) if role == "all" else ("net",))
            rows = []
            for _, r in pooled.iterrows():
                row = _curve_row(r)
                row.update(ci.get(row["bucket"], {}))
                rows.append(row)
            curves[f"{period}|{role}|All"] = rows

            # per-category series, point estimates only
            per_cat = calibration.bucket_stats(sums, group_cols=("category",))
            for cat, sub in per_cat.groupby("category"):
                if cat == "unknown":
                    continue
                curves[f"{period}|{role}|{cat}"] = [
                    _curve_row(r) for _, r in sub.sort_values("bucket").iterrows()]
    return curves


def _block_to_bar(name, block) -> dict:
    """A stat_block -> one bar (headline 80-97c net EV, in cents, with CI)."""
    return {
        "label": name,
        "net_c": _round((block.get("ev_net_pc") or 0) * 100, 3),
        "ci_lo": _round((block["ci_lo"] * 100) if block.get("ci_lo") is not None else None, 3),
        "ci_hi": _round((block["ci_hi"] * 100) if block.get("ci_hi") is not None else None, 3),
        "n": int(block.get("n") or 0),
        "n_events": int(block.get("n_events") or 0),
    }


def main(db_path: str = "data/kalshi.duckdb",
         out_path: str = "web/data/stats.json") -> int:
    con = db.connect(db_path)

    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("series", "events", "markets", "trades")}
    span = con.execute(
        "SELECT min(created_time), max(created_time) FROM trades").fetchone()

    print("[site-data] computing calibration + net-EV curves ...", flush=True)
    curves = build_curves(con)

    print("[site-data] computing headline stats (maker 80-97c) ...", flush=True)
    h = calibration.headline(con)  # {period: {overall, by_category, by_liq_tercile, by_tte, ...}}

    def bars(period, key):
        return [_block_to_bar(name, blk)
                for name, blk in h[period][key].items() if name != "unknown"]

    pre_ev = h["pre"]["overall"]["ev_net_pc"] or 0
    post_ev = h["post"]["overall"]["ev_net_pc"] or 0
    attenuation = round(100 * (pre_ev - post_ev) / pre_ev, 1) if pre_ev else None

    data = {
        "meta": {
            "publication_date": "2025-09-18",  # SSRN publication; panel.PUBLICATION_TS
            "window_start": "2024-01-01",
            "maker_band_c": [int(calibration.MAKER_RANGE[0] * 100),
                             int(calibration.MAKER_RANGE[1] * 100)],
            "n_trades": counts["trades"],
            "n_markets": counts["markets"],
            "trade_span": [str(span[0])[:10], str(span[1])[:10]],
            "roles": list(ROLES),
            "periods": list(PERIODS),
            "categories": sorted({k.split("|")[2] for k in curves} - {"All"}),
        },
        "kpi": {
            "post": _block_to_bar("post", h["post"]["overall"]),
            "pre": _block_to_bar("pre", h["pre"]["overall"]),
            "attenuation_pct": attenuation,
        },
        "curves": curves,
        "by_category": {p: bars(p, "by_category") for p in PERIODS},
        "by_category_liquid": {p: bars(p, "by_category_liquid") for p in PERIODS},
        "by_liq_tercile": {p: bars(p, "by_liq_tercile") for p in PERIODS},
        "by_tte": {p: bars(p, "by_tte") for p in PERIODS},
    }
    con.close()

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":")))
    kb = out.stat().st_size / 1024
    print(f"[site-data] wrote {out} ({kb:.0f} KB, {len(curves)} curves)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
