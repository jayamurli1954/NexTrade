"""ARASS trade filters + deterministic Trade Score (AI-layer proxy)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

import pandas as pd

from research.arass.definition import ArassParams
from research.arass.indicators import clamp


# Hard-coded high-impact Indian event dates (extend as needed). Research avoid list.
DEFAULT_EVENT_DATES: Set[str] = {
    # Union Budget (recent / sample)
    "2016-02-29",
    "2017-02-01",
    "2018-02-01",
    "2019-02-01",
    "2020-02-01",
    "2021-02-01",
    "2022-02-01",
    "2023-02-01",
    "2024-02-01",
    "2025-02-01",
    "2026-02-01",
    # Sample RBI policy / election result markers (incomplete — maintain externally)
    "2019-05-23",
    "2024-06-04",
}


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    reasons: tuple
    scores: Dict[str, float]
    trade_score: float


def _score_band(value: float, lo: float, hi: float, *, invert_edges: bool = True) -> float:
    """
    Map value in [lo,hi] -> 70..100 (center best). Outside band -> 0.
    Floor keeps TradeScore usable after hard filters already passed.
    """
    if value < lo or value > hi:
        return 0.0
    mid = 0.5 * (lo + hi)
    half = 0.5 * (hi - lo) or 1.0
    dist = abs(value - mid) / half
    if invert_edges:
        return clamp(70.0 + 30.0 * (1.0 - dist), 0.0, 100.0)
    return 100.0


def _score_lower_better(value: float, limit: float) -> float:
    """0 outside/at-limit; 70..100 as value approaches 0."""
    if value < 0:
        value = abs(value)
    if value >= limit:
        return 0.0
    return clamp(70.0 + 30.0 * (1.0 - value / max(limit, 1e-6)), 0.0, 100.0)


def evaluate_filters(
    *,
    ts: pd.Timestamp,
    spot: float,
    vwap: float,
    ema20: float,
    ema50: float,
    adx_val: float,
    vix: float,
    gap_pct: float,
    opening_range_pct: float,
    params: ArassParams,
    event_dates: Optional[Set[str]] = None,
) -> FilterResult:
    reasons = []
    scores: Dict[str, float] = {}
    events = event_dates if event_dates is not None else DEFAULT_EVENT_DATES
    day_key = str(pd.Timestamp(ts).date())

    wd = int(pd.Timestamp(ts).weekday())
    if wd not in params.trade_weekdays:
        reasons.append("weekday_blocked")
    if wd == 3 and params.thursday_morning_only:
        hm = (ts.hour, ts.minute)
        if hm > params.entry_end_hm:
            reasons.append("thursday_afternoon_blocked")

    # Expiry afternoon avoid (Thursday after 12:00)
    if wd == 3 and (ts.hour > 12 or (ts.hour == 12 and ts.minute >= 0)):
        if "thursday_afternoon_blocked" not in reasons:
            reasons.append("expiry_afternoon_avoid")

    if day_key in events:
        reasons.append("event_calendar_avoid")
        scores["event"] = 0.0
    else:
        scores["event"] = 100.0

    if not (params.vix_min < vix < params.vix_max):
        reasons.append("vix_out_of_band")
    scores["volatility"] = _score_band(vix, params.vix_min, params.vix_max)

    if spot <= 0 or vwap <= 0:
        reasons.append("bad_price")
        vwap_dev = 999.0
    else:
        vwap_dev = abs(spot - vwap) / vwap * 100.0
    if vwap_dev > params.vwap_band_pct:
        reasons.append("away_from_vwap")
    scores["vwap"] = _score_lower_better(vwap_dev, params.vwap_band_pct)

    ema_spread = abs(ema20 - ema50) / max(spot, 1e-6) * 100.0
    if ema_spread > params.ema_align_pct:
        reasons.append("ema_not_aligned")
    scores["trend"] = _score_lower_better(ema_spread, params.ema_align_pct)

    if adx_val >= params.adx_max:
        reasons.append("adx_high")
    scores["momentum"] = _score_lower_better(adx_val, params.adx_max)

    if opening_range_pct > params.opening_range_max_pct:
        reasons.append("opening_range_wide")
    scores["breadth"] = _score_lower_better(opening_range_pct, params.opening_range_max_pct)

    if abs(gap_pct) >= params.gap_max_pct:
        reasons.append("gap_too_large")
    scores["gap"] = _score_lower_better(abs(gap_pct), params.gap_max_pct)

    # PCR / OI placeholders until historical feeds wired — neutral 80
    scores["pcr"] = 80.0
    scores["oi"] = 80.0

    weights = {
        "volatility": 0.18,
        "trend": 0.14,
        "momentum": 0.14,
        "vwap": 0.12,
        "breadth": 0.10,
        "gap": 0.10,
        "event": 0.12,
        "pcr": 0.05,
        "oi": 0.05,
    }
    trade_score = sum(scores[k] * w for k, w in weights.items())
    if trade_score < params.trade_score_min:
        reasons.append("trade_score_below_min")

    allowed = len(reasons) == 0
    return FilterResult(
        allowed=allowed,
        reasons=tuple(reasons),
        scores=scores,
        trade_score=float(trade_score),
    )
