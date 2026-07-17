"""One-off physical dedupe of the trades table, month by month.

Duplicates are byte-identical re-inserted pages (collector kill/resume
overlaps), so full-row DISTINCT per month is exact. Month partitions bound
peak memory and temp disk to one month's data (~5-8 GB).
"""
import sys

from kalshi_flb import db


def main(db_path="data/kalshi.duckdb", from_month=""):
    con = db.connect(db_path)
    months = [r[0] for r in con.execute(
        "SELECT DISTINCT date_trunc('month', created_time) FROM trades "
        "ORDER BY 1").fetchall()]
    if from_month:
        months = [m for m in months if str(m) >= from_month]
    total_removed = 0
    for mo in months:
        pred = ("created_time >= ? AND "
                "created_time < ? + INTERVAL 1 MONTH")
        before = con.execute(
            f"SELECT count(*) FROM trades WHERE {pred}", [mo, mo]).fetchone()[0]
        # on-disk swap table, NOT temp: temp tables are memory-resident and
        # the biggest months (~1e8 rows) blow past the duckdb memory limit
        con.execute("BEGIN")
        con.execute(f"CREATE OR REPLACE TABLE _mo_swap AS "
                    f"SELECT DISTINCT * FROM trades WHERE {pred}", [mo, mo])
        con.execute(f"DELETE FROM trades WHERE {pred}", [mo, mo])
        con.execute("INSERT INTO trades SELECT * FROM _mo_swap")
        con.execute("DROP TABLE _mo_swap")
        con.execute("COMMIT")
        after = con.execute(
            f"SELECT count(*) FROM trades WHERE {pred}", [mo, mo]).fetchone()[0]
        removed = before - after
        total_removed += removed
        print(f"{str(mo)[:7]}: {before:,} -> {after:,} (-{removed:,})",
              flush=True)
        con.execute("CHECKPOINT")
    print(f"TOTAL removed: {total_removed:,}")
    con.close()


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
