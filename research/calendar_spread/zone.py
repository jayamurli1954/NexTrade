"""20-session zone lean (CAL-0)."""

from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from research.arass.indicators import atm_strike


def zone_bounds(high: pd.Series, low: pd.Series, lookback: int = 20) -> Tuple[pd.Series, pd.Series]:
    """Prior N-session high/low (shifted so today does not peek)."""
    prior_high = high.rolling(lookback).max().shift(1)
    prior_low = low.rolling(lookback).min().shift(1)
    return prior_high, prior_low


def zone_lean(spot: float, zone_high: float, zone_low: float) -> Optional[str]:
    """
    Upper third → CE, lower third → PE, middle → None (no entry).
    """
    try:
        zh = float(zone_high)
        zl = float(zone_low)
        px = float(spot)
    except (TypeError, ValueError):
        return None
    span = zh - zl
    if span <= 0 or px != px:
        return None
    pos = (px - zl) / span
    if pos >= 2.0 / 3.0:
        return "CE"
    if pos <= 1.0 / 3.0:
        return "PE"
    return None


def select_strike(
    spot: float,
    lean: str,
    *,
    zone_high: float,
    zone_low: float,
    strike_step: float = 50.0,
    offset_toward_extreme: bool = True,
) -> float:
    """ATM rounded to step; optional ±1 step toward zone extreme."""
    base = atm_strike(float(spot), float(strike_step))
    if not offset_toward_extreme:
        return float(base)
    mid = (float(zone_high) + float(zone_low)) / 2.0
    step = float(strike_step)
    if lean.upper() == "CE" and float(spot) >= mid:
        return float(base + step)
    if lean.upper() == "PE" and float(spot) <= mid:
        return float(base - step)
    return float(base)


def overnight_gap_pct(open_px: float, prior_close: float) -> float:
    """abs(open − prior_close) / prior_close * 100."""
    try:
        o = float(open_px)
        c = float(prior_close)
    except (TypeError, ValueError):
        return 0.0
    if c <= 0:
        return 0.0
    return abs(o - c) / c * 100.0
