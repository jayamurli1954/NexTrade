"""Indicators and Black-Scholes helpers for ARASS research."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return true_range(high, low, close).rolling(period).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(high, low, close)
    atr_s = tr.rolling(period).mean()
    plus_di = 100.0 * pd.Series(plus_dm, index=close.index).rolling(period).mean() / atr_s.replace(0, np.nan)
    minus_di = 100.0 * pd.Series(minus_dm, index=close.index).rolling(period).mean() / atr_s.replace(0, np.nan)
    dx = (100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    return dx.rolling(period).mean()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday VWAP reset each calendar day. Falls back to typical price if volume missing."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    vol = vol.replace(0, np.nan).fillna(1.0)
    day = df.index.date
    cum_pv = (tp * vol).groupby(day).cumsum()
    cum_v = vol.groupby(day).cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(
    spot: float,
    strike: float,
    t_years: float,
    iv: float,
    rate: float,
    option_type: str,
) -> float:
    """European BS price. option_type in {'CE','PE'}."""
    if spot <= 0 or strike <= 0 or iv <= 0:
        return max(0.0, (spot - strike) if option_type == "CE" else (strike - spot))
    t = max(float(t_years), 1.0 / (365.0 * 24.0 * 12.0))  # floor ~5 minutes
    vol = max(float(iv), 1e-6)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    if option_type.upper() == "CE":
        return float(spot * _norm_cdf(d1) - strike * math.exp(-rate * t) * _norm_cdf(d2))
    return float(strike * math.exp(-rate * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1))


def atm_strike(spot: float, step: float = 50.0) -> float:
    return round(spot / step) * step


def years_to_expiry(now: pd.Timestamp, expiry: pd.Timestamp) -> float:
    delta = (expiry - now).total_seconds()
    return max(delta / (365.0 * 24.0 * 3600.0), 0.0)


def nearest_thursday_expiry(day: pd.Timestamp) -> pd.Timestamp:
    """Weekly expiry proxy = upcoming Thursday 15:30 IST (research default)."""
    d = pd.Timestamp(day).tz_localize(None) if getattr(day, "tzinfo", None) else pd.Timestamp(day)
    d = d.normalize()
    # Mon=0 ... Sun=6
    wd = int(d.weekday())
    days_ahead = (3 - wd) % 7
    if days_ahead == 0 and (day.hour > 15 or (day.hour == 15 and day.minute >= 30)):
        days_ahead = 7
    exp = d + pd.Timedelta(days=days_ahead)
    return exp + pd.Timedelta(hours=15, minutes=30)


def nifty_lot_size(day: pd.Timestamp, default: int = 65) -> int:
    """Approximate historical NIFTY lot sizes (research; confirm before live)."""
    d = pd.Timestamp(day).tz_localize(None) if getattr(day, "tzinfo", None) else pd.Timestamp(day)
    # Rough calendar: 50 for long stretch; 25 after Sep-2024 revision; else configured default.
    if d < pd.Timestamp("2024-09-20"):
        return 50
    if d < pd.Timestamp("2025-04-01"):
        return 25
    return int(default)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
