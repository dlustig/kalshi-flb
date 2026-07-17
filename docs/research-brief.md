# Research provenance — why build a Kalshi favorite–longshot bias verifier

> **This is a trimmed excerpt.** The source was a broad, truth-first research
> brief surveying conservative-income and systematic-retail strategies. Only the
> sections that motivate *this* project — the Kalshi favorite–longshot bias and
> its maker-side mechanics — are reproduced below.
>
> The organizing principle of the parent brief was to **seek edges in structure
> and capacity constraints, not prediction** — places big money can't or won't
> go. Of every candidate evaluated, the Kalshi bias was the strongest
> *structural*, retail-scale, rule-based edge, and the one chosen for a
> read-only verification pass before any capital is committed. This repository
> is that pass: **step 1 of a staged GO decision** (see the "Verdict / staged
> plan" at the end).

## The finding (research iteration 1, July 2026)

**Prediction markets (Kalshi) — strongest candidate.**

- First systematic academic study (Bürgi, Deng & Whelan; SSRN 2025 / UCD WP;
  ~314k contracts, transaction-level): prices are informative but show a clear
  favorite–longshot bias. Contracts <10¢ lose >60% of buyer capital; high-price
  contracts win slightly more often than priced, yielding small positive returns.
- Independent analysis of 72.1M trades / $18.26B volume (Becker, Jan 2026): 5¢
  contracts win 4.18% of the time; 95¢ contracts win 95.83%. The bias is
  consistent below 20¢ and above 80¢.
- Microstructure matters: makers (limit orders) materially outperform takers
  (market orders); paying for immediacy is costliest at the longshot end
  (CEPR/Whelan, Feb 2026).
- Caveats: the edge at the favorite end is small-positive (singles, not home
  runs); the authors explicitly question whether the pattern persists after
  publication.
- **Verdict:** real, documented, retail-scale, CFTC-regulated, and rule-based
  (buy favorites as a maker; never buy longshots as a taker). The most promising
  idea surfaced — to be sized as a small experimental sleeve only.

**Meta-finding across the whole brief:** every edge that survived scrutiny was
*structural* (a rule, a documented behavioral bias, a persistent risk premium);
every edge that wilted was *predictive*.

**Legal note (binding constraint):** all work uses publicly available data only
(Kalshi's public, no-auth market-data API). No authenticated, privileged, or
employer-accessed data — categorically excluded.

## Deep dive — Kalshi maker-side mechanics (research iteration 2, July 2026)

**Fees (favorable for the favorite-side maker strategy):**

- Taker fee = 0.07 × P × (1−P); peaks at 1.75¢/contract at 50¢, falls to 0.63¢
  at 90¢ and 0.33¢ at 95¢ — cheapest exactly where the documented edge lives.
- Maker fee = 25% of taker; most standard markets 0% maker, but major events
  (championships/elections) charge a flat 0.25% maker. Fees round UP per trade —
  the effective rate exceeds the formula at small size.
- Idle cash earns ~4% APY — collateral earns roughly the risk-free benchmark
  while resting; the edge stacks on that floor.
- Liquidity Incentive Program (through Sep 1, 2026): daily rewards $10–$1,000 for
  resting orders. The venue currently subsidizes the maker side.

**API (professional-grade, free):**

- Public market data (prices, books, trades, historical) with no auth; trading
  via API-key + RSA-PSS; REST + WebSocket + FIX 4.4; demo environment; batch
  order/cancel; token-bucket rate limits with volume-earned tiers.
- Rate limits preclude HFT; medium-frequency / event-driven is the design point
  (which fits this strategy).
- Live/historical data-tier split (Feb 2026): settled markets move to
  `/historical` endpoints — relevant for backtest dataset construction.

**Capacity (hard ceiling, from the academic authors directly):**

- Top-decile markets average only ~$526k final volume; order-book depth at any
  moment is far smaller; large maker size forces worse posted prices; ~40% of
  maker orders never fill (model match rate 0.60).
- Conclusion: working capital of hundreds to low thousands of dollars. A sleeve,
  never a salary.

**Primary risk — adverse selection (the maker's negative-skew trap):**

- Resting orders get filled disproportionately when the world has moved against
  you (news you haven't seen). The "maker rebate" is not free money.
- Mitigations are engineering: quote only markets with an independent probability
  model, cancel/requote on news, never leave stale orders unattended, log fill
  quality.

**Taxes (assessed, not optimistic):**

- §1256 (60/40) treatment for event contracts is UNSETTLED: no IRS guidance;
  binary event contracts don't clearly fit statutory categories; claiming it is
  an aggressive position (Form 8275 disclosure advised). The CFTC's
  classification of event contracts as binary-option "swaps" may trigger the
  §1256(b)(2)(B) exclusion.
- Conservative planning assumption: ordinary income. Kalshi issues no 1099-B for
  event trades — self-reporting is required; any bot must log every fill from
  day one.

**Market selection:**

- Depth concentrates in US politics and economics (tightest spreads); Fed-rate
  markets are liquid enough to serve as a Federal Reserve staff-paper data source
  (recent volumes >$1M per strike).
- Weather: a small loyal niche, thin books, data-print gap risk — phase 3 only,
  contingent on building a real NOAA-data probability model (the informed side of
  a thin book: highest edge potential, lowest capacity).

**Verdict: GO, at experiment scale.** Staged plan:

1. **Build a read-only collector against the public API; measure whether the
   favorite–longshot bias persists in *current* data, net of fees** (the authors
   warn publication may erode it — verify first). **← this repository.**
2. Paper-trade the maker logic in the demo environment.
3. Go live with a few hundred dollars: favorite-side maker orders only, hard
   position caps, full fill logging.
4. Walk-away criteria: measured live bias net of fees ≤ 0, or fill-quality
   analysis shows adverse selection consuming the edge.
