"""kalshi-flb CLI: backfill / sync / status / export / report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import collector, db

DEFAULT_DB = "data/kalshi.duckdb"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kalshi-flb")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("backfill", "sync", "status", "export", "report"):
        s = sub.add_parser(name)
        s.add_argument("--db", default=DEFAULT_DB)
        if name in ("backfill", "sync"):
            s.add_argument("--rps", type=float, default=8.0)
        if name == "backfill":
            s.add_argument("--max-pages", type=int, default=None,
                           help="cap pages per stream (smoke tests)")
        if name == "status":
            s.add_argument("--json", action="store_true")
        if name == "export":
            s.add_argument("--out", default="data/parquet")
        if name == "report":
            s.add_argument("--out", default="analysis/out")
    a = p.parse_args(argv)

    if a.cmd == "backfill":
        counts = collector.backfill(a.db, rps=a.rps, max_pages=a.max_pages)
        print(json.dumps(counts))
    elif a.cmd == "sync":
        print(json.dumps(collector.sync(a.db, rps=a.rps)))
    elif a.cmd == "status":
        try:
            st = collector.status(a.db)
        except Exception as e:  # duckdb lock: single writer holds the file
            if "lock" in str(e).lower():
                print("DB is locked by the running collector. Live progress is "
                      "on the collector's stderr (one line per 25 pages).",
                      file=sys.stderr)
                return 2
            raise
        if a.json:
            print(json.dumps(st, default=str))
        else:
            for k, v in st["tables"].items():
                print(f"{k:10} {v:>12,}")
            for name, s in st["streams"].items():
                print(f"{name:14} done={s['done']} rows={s['rows']:,} "
                      f"wm={s['watermark']}")
            print(f"trades span: {st['trades_span'][0]} .. {st['trades_span'][1]}")
            if st.get("trades_hist_eta_hours") is not None:
                print(f"trades_hist ETA: ~{st['trades_hist_eta_hours']}h")
    elif a.cmd == "export":
        con = db.connect(a.db)
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for t in ("series", "events", "markets", "trades"):
            con.execute(f"COPY {t} TO '{out / t}.parquet' (FORMAT PARQUET)")
        print(f"exported to {out}/")
    elif a.cmd == "report":
        from . import report
        path = report.generate(a.db, a.out)
        print(f"report written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
