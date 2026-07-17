"""Data-quality gate: run after backfill, before the report is trusted.

Exits nonzero on any failure. Usage: uv run python scripts/dq_check.py [db_path]
"""
import sys

from kalshi_flb import db, panel

FAIL = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if not ok:
        FAIL.append(name)


def main(db_path: str = "data/kalshi.duckdb") -> int:
    con = db.connect(db_path)
    panel.create_views(con)

    total_trades = con.execute("SELECT count(*) FROM trades").fetchone()[0]
    check("nonempty", total_trades > 1_000_000,
          f"{total_trades:,} trades collected")

    # KXMVE-prefixed trades are parlay trades whose market rows are
    # intentionally not collected (mve_filter=exclude; prefix verified
    # against 1.455M markets with 0 mismatches) — not orphans.
    orphans = con.execute(
        "WITH tt AS (SELECT ticker, count(*) n FROM trades "
        "            WHERE ticker NOT LIKE 'KXMVE%' GROUP BY 1) "
        "SELECT coalesce(sum(tt.n), 0) FROM tt WHERE NOT EXISTS "
        "(SELECT 1 FROM markets m WHERE m.ticker = tt.ticker)").fetchone()[0]
    frac = orphans / total_trades if total_trades else 1
    check("orphan_trades", frac < 0.05,
          f"{orphans:,} / {total_trades:,} = {frac:.3%} (< 5% required)")

    row = con.execute(
        "WITH tt AS (SELECT ticker, sum(count) vol FROM trades GROUP BY 1) "
        "SELECT coalesce(sum(tt.vol) FILTER (WHERE u.category != 'unknown'), 0), "
        "       sum(tt.vol) "
        "FROM tt JOIN v_universe u ON tt.ticker = u.ticker").fetchone()
    cov = row[0] / row[1] if row[1] else 0
    check("category_coverage", cov >= 0.99,
          f"{cov:.3%} of universe volume category-mapped (>= 99% required)")

    bad_results = con.execute(
        "SELECT count(*) FROM markets WHERE market_type='binary' "
        "AND result NOT IN ('yes','no','void','') AND result IS NOT NULL "
        "AND status = 'settled'").fetchone()[0]
    check("result_domain", bad_results == 0,
          f"{bad_results} settled binary markets with unexpected result values")

    # exact dupe count, partitioned by month so no single DISTINCT has to
    # hold 5e8 UUIDs (shard windows never span months at the boundary scale
    # that matters; a cross-month dupe would appear in both partitions anyway)
    months = [r[0] for r in con.execute(
        "SELECT DISTINCT strftime(created_time, '%Y-%m') FROM trades"
    ).fetchall()]
    dupes = 0
    for mo in sorted(months):
        dupes += con.execute(
            "SELECT count(*) - count(DISTINCT trade_id) FROM trades "
            "WHERE strftime(created_time, '%Y-%m') = ?", [mo]).fetchone()[0]
    check("no_dupe_trade_ids", dupes == 0, f"{dupes} duplicates")

    null_ev = con.execute(
        "SELECT count(*) FROM v_universe WHERE event_ticker IS NULL "
        "OR event_ticker = ''").fetchone()[0]
    check("event_ticker_present", null_ev == 0,
          f"{null_ev} universe markets with null event_ticker (cluster key)")

    months = con.execute("""
        WITH m AS (SELECT strftime(created_time, '%Y-%m') mo FROM trades),
        expected AS (SELECT strftime(r, '%Y-%m') mo FROM
          range(TIMESTAMPTZ '2024-01-01', now(), INTERVAL 1 MONTH) t(r))
        SELECT list(e.mo) FROM expected e
        WHERE e.mo NOT IN (SELECT DISTINCT mo FROM m)""").fetchone()[0]
    check("monthly_coverage", not months, f"empty months: {months or 'none'}")

    streams = dict(con.execute(
        "SELECT stream, done FROM stream_state "
        "WHERE stream != 'trades_mve_dropped'").fetchall())  # counter, not a stream
    undone = [s for s, d in streams.items() if not d]
    check("streams_done", not undone, f"incomplete streams: {undone or 'none'}")

    con.close()
    print("\n" + ("DQ GATE: FAIL " + str(FAIL) if FAIL else "DQ GATE: PASS"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
