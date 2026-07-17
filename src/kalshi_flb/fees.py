"""Kalshi fee schedule as data + math, with a SQL twin for in-DB aggregation.

Schedule facts and their verification status live in docs/kalshi-api-notes.md:
- taker = 0.07 * fee_multiplier * C * P * (1-P), rounded UP
- maker = 0 on `quadratic` series; 25% of the taker formula on
  `quadratic_with_maker_fees`; `flat` semantics unverified -> NaN sentinel
  (panel excludes and counts those rows)
- rounding quantum: $0.01 before ROUNDING_ERA_BOUNDARY, $0.0001 after.
  The boundary date (2026-02-05, from the research brief) is NOT confirmed by
  the API changelog; report runs a sensitivity check on it.
TAKER_COEF/MAKER_FRACTION re-verified against the official fee PDF in Task 10.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal

TAKER_COEF = 0.07
MAKER_FRACTION = 0.25
ROUNDING_ERA_BOUNDARY = datetime(2026, 2, 5, tzinfo=UTC)

_QUANTA = {"0.01": Decimal("0.01"), "0.0001": Decimal("0.0001")}


def round_up(x: float, quantum: str) -> float:
    """Round x UP to the given quantum, tolerating float representation noise."""
    d = Decimal(str(round(x, 9)))
    return float(d.quantize(_QUANTA[quantum], rounding=ROUND_CEILING))


def _quantum_for(ts: datetime) -> str:
    return "0.01" if ts < ROUNDING_ERA_BOUNDARY else "0.0001"


def taker_fee(price: float, count: float, multiplier: float, ts: datetime) -> float:
    raw = TAKER_COEF * multiplier * count * price * (1.0 - price)
    return round_up(raw, _quantum_for(ts))


def maker_fee(price: float, count: float, multiplier: float,
              fee_type: str, ts: datetime) -> float:
    if fee_type == "quadratic":
        return 0.0
    if fee_type == "quadratic_with_maker_fees":
        raw = MAKER_FRACTION * TAKER_COEF * multiplier * count * price * (1.0 - price)
        return round_up(raw, _quantum_for(ts))
    return math.nan  # `flat` (or unknown): unverified semantics, exclude+count


def _sql_round_up(expr: str, ts_col: str, rounding: str | None = None) -> str:
    # ceil() after a 9dp pre-round, mirroring round_up(); era picks the quantum.
    # `rounding` in ('cent', 'centicent') forces one era — sensitivity analysis.
    cent = f"ceiling(round(({expr}) * 100, 7)) / 100"
    centicent = f"ceiling(round(({expr}) * 10000, 5)) / 10000"
    if rounding == "cent":
        return f"({cent})"
    if rounding == "centicent":
        return f"({centicent})"
    return (
        f"(CASE WHEN {ts_col} < TIMESTAMPTZ '2026-02-05 00:00:00+00' "
        f"THEN {cent} ELSE {centicent} END)"
    )


def sql_taker_fee(price_col: str, count_col: str, mult_col: str, ts_col: str,
                  rounding: str | None = None) -> str:
    expr = f"{TAKER_COEF} * {mult_col} * {count_col} * {price_col} * (1.0 - {price_col})"
    return _sql_round_up(expr, ts_col, rounding)


def sql_maker_fee(price_col: str, count_col: str, mult_col: str, ts_col: str,
                  fee_type_col: str, rounding: str | None = None) -> str:
    expr = (f"{MAKER_FRACTION} * {TAKER_COEF} * {mult_col} * {count_col} "
            f"* {price_col} * (1.0 - {price_col})")
    return (
        f"(CASE {fee_type_col} "
        f"WHEN 'quadratic' THEN 0.0 "
        f"WHEN 'quadratic_with_maker_fees' THEN {_sql_round_up(expr, ts_col, rounding)} "
        f"ELSE 'nan'::DOUBLE END)"
    )
