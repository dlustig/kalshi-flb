"""Reproducible report + VERDICT generation.

Chart styling follows the dataviz skill's reference palette (validated
instance, light mode): categorical slots in fixed order, chrome inks, one
axis, zero baseline, thin marks, direct labels + legend.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import calibration, db, panel  # noqa: E402

# dataviz reference palette (light mode) — pre-validated set, used verbatim
SERIES_1 = "#2a78d6"   # slot 1 blue
SERIES_2 = "#1baf7a"   # slot 2 aqua (sub-3:1 on light -> direct labels shipped)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

MAKER_LO, MAKER_HI = calibration.MAKER_RANGE


def _style_ax(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=12)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)


def _series_with_ci(con, *, role, period, bucket_col="bucket_5c"):
    """Per-bucket stats for one (role, period) slice, with clustered 95% CIs on
    both the win rate and net EV attached as `*_lo`/`*_hi` columns. Returns None
    for an empty slice (the plotters skip it)."""
    sums = calibration.event_sums(con, bucket_col=bucket_col, role=role,
                                  where=f"period = '{period}'")
    if sums.empty:
        return None
    stats = calibration.bucket_stats(sums).sort_values("bucket")

    def ci_by_bucket(num_col):
        # each bucket's ratio-of-sums bootstrapped separately, events resampled
        pairs = [calibration.cluster_bootstrap(sums[sums["bucket"] == b], num_col, "n")
                 for b in stats["bucket"]]
        return [lo for lo, _ in pairs], [hi for _, hi in pairs]

    stats["wr_lo"], stats["wr_hi"] = ci_by_bucket("wins")
    stats["net_lo"], stats["net_hi"] = ci_by_bucket("net")
    return stats


def _plot_calibration(series: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    _style_ax(ax, "Calibration deviation by 5¢ bucket (all roles)",
              "volume-weighted mean price (¢)", "win rate − price (pp)")
    ax.axhline(0, color=BASELINE, linewidth=1)
    for (label, stats), color in zip(series.items(), (SERIES_1, SERIES_2)):
        if stats is None:
            continue
        x = stats["mean_price"] * 100
        y = (stats["win_rate"] - stats["mean_price"]) * 100
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5,
                label=label)
        ax.fill_between(x, (stats["wr_lo"] - stats["mean_price"]) * 100,
                        (stats["wr_hi"] - stats["mean_price"]) * 100,
                        color=color, alpha=0.15, linewidth=0)
        ax.annotate(label, (x.iloc[-1], y.iloc[-1]), color=color, fontsize=9,
                    xytext=(6, 0), textcoords="offset points", va="center")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, dpi=144, facecolor=SURFACE)
    plt.close(fig)


def _plot_net_return(series: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    _style_ax(ax, "Net expected return per contract, post-publication",
              "volume-weighted mean price (¢)", "net EV (¢/contract)")
    ax.axhline(0, color=BASELINE, linewidth=1)
    for (label, stats), color in zip(series.items(), (SERIES_1, SERIES_2)):
        if stats is None:
            continue
        x = stats["mean_price"] * 100
        y = stats["ev_net_pc"] * 100
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5,
                label=label)
        ax.fill_between(x, stats["net_lo"] * 100, stats["net_hi"] * 100,
                        color=color, alpha=0.15, linewidth=0)
        ax.annotate(label, (x.iloc[-1], y.iloc[-1]), color=color, fontsize=9,
                    xytext=(6, 0), textcoords="offset points", va="center")
    ax.axvspan(MAKER_LO * 100, MAKER_HI * 100, color=GRID, alpha=0.35,
               linewidth=0)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, dpi=144, facecolor=SURFACE)
    plt.close(fig)


def _fmt_stat(s: dict) -> str:
    if not s or s["n"] == 0 or s["ev_net_pc"] is None:
        return "| — | — | — | — | — |"
    ci = ("[n/a]" if s["ci_lo"] is None or s["ci_lo"] != s["ci_lo"]
          else f"[{s['ci_lo'] * 100:+.2f}, {s['ci_hi'] * 100:+.2f}]")
    return (f"| {s['n']:,.0f} | {s['n_events']:,} | "
            f"{s['ev_net_pc'] * 100:+.3f}¢ | {ci} | "
            f"{s['ev_net_pct'] * 100:+.2f}% |")


def _stat_table(title: str, blocks: dict) -> list[str]:
    out = [f"### {title}", "",
           "| segment | n contracts | n events | net EV/contract | 95% CI (¢) | net EV %/$ |",
           "|---|---|---|---|---|---|"]
    for name, s in blocks.items():
        out.append(f"| {name} " + _fmt_stat(s))
    out.append("")
    return out


def _is_go(h: dict) -> tuple[bool, list[str]]:
    """Pre-committed criteria: GO iff a liquid (tercile-3) category has
    positive post-period maker net EV with 95% CI excluding zero."""
    winners = []
    for cat, s in h["post"].get("by_category_liquid", {}).items():
        ev, lo = s.get("ev_net_pc"), s.get("ci_lo")
        if ev is not None and ev > 0 and lo is not None and lo == lo and lo > 0:
            winners.append(cat)  # lo == lo filters NaN CIs (too few events)
    return bool(winners), winners


def _fee_drift_note(con) -> str:
    """Quantify exposure to per-series fee changes (fees use current params)."""
    n_changes = con.execute("SELECT count(*) FROM fee_changes").fetchone()[0]
    if n_changes == 0:
        return ("- Fee-drift exposure: **unknown** — the `/series/fee_changes` "
                "history has not been collected into this DB (0 rows). Run "
                "`kalshi-flb sync` and regenerate before trusting net-of-fee "
                "levels on fee-changed series.")
    row = con.execute("""
        WITH tt AS (SELECT ticker, sum(count) AS vol FROM trades GROUP BY 1)
        SELECT coalesce(sum(tt.vol) FILTER (WHERE u.series_ticker IN
                 (SELECT series_ticker FROM fee_changes)), 0),
               sum(tt.vol)
        FROM tt JOIN v_universe u ON tt.ticker = u.ticker""").fetchone()
    affected, total = row
    pct = 100.0 * affected / total if total else 0.0
    return (f"- Fee-drift exposure: fees use each series' *current* fee params; "
            f"{pct:.2f}% of panel contract volume sits on series with ≥1 of "
            f"the {n_changes} recorded fee changes (`/series/fee_changes` "
            f"history). If material, re-run with time-aware fee params.")


def generate_from_con(con, out_dir) -> Path:
    out = Path(out_dir)
    (out / "plots").mkdir(parents=True, exist_ok=True)
    panel.create_views(con)
    agg_rows = panel.create_agg(con)  # the single heavy scan

    ex = panel.exclusions(con)
    h = calibration.headline(con)
    cal = {"pre": _series_with_ci(con, role="all", period="pre"),
           "post": _series_with_ci(con, role="all", period="post")}
    net = {"maker": _series_with_ci(con, role="maker", period="post"),
           "taker": _series_with_ci(con, role="taker", period="post")}
    _plot_calibration(cal, out / "plots" / "calibration_pre_post.png")
    _plot_net_return(net, out / "plots" / "net_return_by_bucket.png")

    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("series", "events", "markets", "trades")}
    span = con.execute(
        "SELECT min(created_time), max(created_time) FROM trades").fetchone()
    monthly = con.execute(
        "SELECT strftime(created_time, '%Y-%m') m, count(*) c FROM trades "
        "GROUP BY 1 ORDER BY 1").df()

    # fee-rounding sensitivity: same agg pass, alternate net columns
    sens = {
        mode: calibration.stat_block(calibration.event_sums(
            con, bucket_col=None, role="maker",
            where=f"{calibration.MAKER_WHERE} AND period = 'post'", mode=mode))
        for mode in ("cent", "centicent")
    }

    lines = [
        "# Kalshi favorite–longshot bias — post-publication verification",
        f"\nGenerated {datetime.now(UTC):%Y-%m-%d %H:%M}Z. "
        f"Window: trades ≥ 2024-01-01; decay split at 2025-09-18 (SSRN publication).",
        "\n## Data summary\n",
        "| table | rows |", "|---|---|",
        *[f"| {t} | {n:,} |" for t, n in counts.items()],
        f"\nTrade span: {span[0]} → {span[1]}. "
        f"Aggregated panel: {agg_rows:,} event×bucket×segment cells.",
        "\nMonthly trade counts:\n",
        monthly.to_markdown(index=False),
        "\n### Exclusions\n",
        ex.to_markdown(index=False),
        "\n## Calibration (5¢ buckets, all roles)\n",
        "![calibration](plots/calibration_pre_post.png)\n",
    ]
    for period in ("pre", "post"):
        st = cal[period]
        if st is None:
            lines.append(f"\n_No {period}-period data._\n")
            continue
        lines += [f"\n### {period}\n",
                  "| bucket | n | mean price | win rate | 95% CI |",
                  "|---|---|---|---|---|"]
        for _, r in st.iterrows():
            lines.append(
                f"| {int(r['bucket'])}–{int(r['bucket']) + 4}¢ | {r['n']:,.0f} "
                f"| {r['mean_price'] * 100:.2f}¢ | {r['win_rate'] * 100:.2f}% "
                f"| [{r['wr_lo'] * 100:.2f}, {r['wr_hi'] * 100:.2f}] |")
    lines += [
        "\n## Net returns, post-publication (maker vs taker)\n",
        "![net](plots/net_return_by_bucket.png)\n",
        f"\n## Headline: maker-side net EV, {MAKER_LO * 100:.0f}–{MAKER_HI * 100:.0f}¢\n",
        "(operationalized as 1¢ buckets 80–96, i.e. price ∈ [0.80, 0.97))\n",
    ]
    for period in ("pre", "post"):
        lines += _stat_table(f"{period} — overall",
                             {"overall": h[period]["overall"]})
        lines += _stat_table(f"{period} — by category", h[period]["by_category"])
        lines += _stat_table(f"{period} — by liquidity tercile (3 = most liquid)",
                             h[period]["by_liq_tercile"])
        lines += _stat_table(f"{period} — by time-to-close", h[period]["by_tte"])
        lines += _stat_table(f"{period} — by category, liquid tercile only",
                             h[period]["by_category_liquid"])
    lines += [
        "\n## Fee-rounding sensitivity (post, overall)\n",
        "| rounding forced | net EV/contract | 95% CI |", "|---|---|---|",
        *[f"| {m} |" + "|".join(_fmt_stat(s).split("|")[3:5]) + "|"
          for m, s in sens.items()],
        "\n## Methodology & caveats\n",
        "- Both sides of every trade enter the panel (Whelan-style contract "
        "counting); the built-in Yes/No double count is why all CIs cluster by "
        "`event_ticker` (percentile bootstrap, B=1000).",
        "- Maker returns condition on fills that actually happened — adverse "
        "selection is *embedded* in these estimates, which is what a maker "
        "strategy would actually have earned on the tape (before queue/fill "
        "modeling).",
        "- Fee constants (0.07 taker coefficient, 25% maker fraction) and the "
        "2026-02-05 rounding-era boundary are per the research brief; the "
        "official fee-schedule PDF was unreachable (HTTP 429) at build time — "
        "see sensitivity table above for rounding-era bounds.",
        "- `flat` fee-type series are excluded from net-of-fee statistics "
        "(unverified semantics) and counted in the exclusion table.",
        "- Multivariate (parlay) markets are excluded; they post-date the "
        "paper's sample and their prices are mechanical products of leg "
        "prices. Their market rows are mostly not collected "
        "(`mve_filter=exclude`); their trades are identified by the KXMVE "
        "ticker prefix, verified exact on 1.455M markets (0 mismatches), so "
        "`markets_mve` undercounts (partial collection) while "
        "`trades_mve_by_prefix` is complete.",
        "- Liquidity terciles are NTILE(3) of market `volume_fp` over the full "
        "universe (final volume — a post-hoc segmentation; tercile 3 gates the "
        "verdict, so treat it as descriptive, not tradeable ex ante).",
        "- Per-contract fees amortize each trade's rounded total over its "
        "contracts (`fee(C)/C`), reproducing the tape's actual fees. A small "
        "standalone order rounds on its own total instead: post-2026-02 that "
        "adds ≤ $0.0001 per order (immaterial); under pre-2026-02 cent "
        "rounding it can add up to ~0.1¢/contract on a 10-lot — pre-period "
        "small-order net EV is slightly overstated by this choice.",
        "- Exclusion-table rows overlap (a market can be counted under two "
        "reasons); `markets_null_volume` and `markets_no_series_metadata` are "
        "informational (those markets stay in the panel).",
        _fee_drift_note(con),
    ]
    (out / "report.md").write_text("\n".join(lines))

    go, winners = _is_go(h)
    post = h["post"]["overall"]
    pre = h["pre"]["overall"]
    v = ["# VERDICT", ""]
    v.append("**GO**" if go else "**NO-GO**")
    v += [
        "",
        f"Question: does the favorite-side maker edge (80–97¢) survive "
        f"post-publication (≥ 2025-09-18), net of fees?",
        "",
        f"- Post-publication maker net EV: "
        f"{'n/a' if post['ev_net_pc'] is None else f'{post['ev_net_pc'] * 100:+.3f}¢/contract'} "
        f"(95% CI {'n/a' if post['ci_lo'] is None else f'[{post['ci_lo'] * 100:+.3f}, {post['ci_hi'] * 100:+.3f}]'}), "
        f"n = {post['n']:,.0f} contracts across {post['n_events']:,} events.",
        f"- Pre-publication twin: "
        f"{'n/a' if pre['ev_net_pc'] is None else f'{pre['ev_net_pc'] * 100:+.3f}¢/contract'} "
        f"(95% CI {'n/a' if pre['ci_lo'] is None else f'[{pre['ci_lo'] * 100:+.3f}, {pre['ci_hi'] * 100:+.3f}]'}).",
        f"- Liquid-tercile categories with CI-positive edge: "
        f"{', '.join(winners) if winners else 'none'}.",
        "",
        "Criteria (pre-committed in the spec): GO iff post-publication "
        "maker-side net EV in 80–97¢ is positive with clustered 95% CI "
        "excluding zero in ≥ 1 liquid category. Either answer is a success.",
        "",
        "Capacity note: phase-2 order-book snapshots were not run; capacity "
        "assessment relies on market-level `liquidity_dollars`/`volume_fp` "
        "distributions in the report, not book depth.",
    ]
    (out / "VERDICT.md").write_text("\n".join(v))
    return out


def generate(db_path, out_dir) -> Path:
    con = db.connect(db_path)
    try:
        return generate_from_con(con, out_dir)
    finally:
        con.close()
