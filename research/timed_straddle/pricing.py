"""
Option pricing for the timed-straddle backtest.

Premiums are synthetic Black-Scholes values with IV = India VIX x a calibration ratio.
The ratio table is fitted against *real* NSE daily option prices (open and close) so the
synthetic level matches what weekly options actually traded at, by option type, calendar
days-to-expiry and moneyness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

MINUTES_PER_YEAR = 365.0 * 24.0 * 60.0
EXPIRY_TIME = pd.Timedelta(hours=15, minutes=30)
MIN_T = 5.0 / (252.0 * 375.0)


def _ncdf(x):
    from scipy.special import ndtr

    return ndtr(np.asarray(x, dtype=float))


def _ncdf_scalar(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: float, t: float, iv: float, rate: float, opt: str) -> float:
    """Scalar European Black-Scholes. ``opt`` is 'CE' or 'PE'."""
    intrinsic = max(0.0, spot - strike) if opt == "CE" else max(0.0, strike - spot)
    if spot <= 0 or strike <= 0 or iv <= 0:
        return intrinsic
    t = max(t, MIN_T)
    vs = iv * math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * t) / vs
    d2 = d1 - vs
    disc = math.exp(-rate * t)
    if opt == "CE":
        px = spot * _ncdf_scalar(d1) - strike * disc * _ncdf_scalar(d2)
    else:
        px = strike * disc * _ncdf_scalar(-d2) - spot * _ncdf_scalar(-d1)
    return max(px, intrinsic * disc, 0.05)


def bs_price_vec(spot, strike, t, iv, rate, is_call):
    spot, strike, t, iv = (np.asarray(a, dtype=float) for a in (spot, strike, t, iv))
    t = np.maximum(t, MIN_T)
    vs = iv * np.sqrt(t)
    d1 = (np.log(spot / strike) + (rate + 0.5 * iv * iv) * t) / vs
    d2 = d1 - vs
    disc = np.exp(-rate * t)
    call = spot * _ncdf(d1) - strike * disc * _ncdf(d2)
    put = strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)
    return np.where(is_call, call, put)


def implied_vol_vec(price, spot, strike, t, rate, is_call, lo=0.01, hi=3.0, iters=60):
    """Vectorized bisection IV solver; NaN where price is outside no-arbitrage bounds."""
    price = np.asarray(price, dtype=float)
    a = np.full_like(price, lo)
    b = np.full_like(price, hi)
    p_lo = bs_price_vec(spot, strike, t, a, rate, is_call)
    p_hi = bs_price_vec(spot, strike, t, b, rate, is_call)
    ok = (price > p_lo) & (price < p_hi)
    for _ in range(iters):
        m = 0.5 * (a + b)
        pm = bs_price_vec(spot, strike, t, m, rate, is_call)
        up = pm < price
        a = np.where(up, m, a)
        b = np.where(up, b, m)
    out = 0.5 * (a + b)
    return np.where(ok, out, np.nan)


SESSION_OPEN_MIN = 9 * 60 + 15
SESSION_CLOSE_MIN = 15 * 60 + 30
SESSION_MINUTES = SESSION_CLOSE_MIN - SESSION_OPEN_MIN  # 375
TRADING_MINUTES_PER_YEAR = 252.0 * SESSION_MINUTES


# Weight on trading-time vs calendar-time. Fitted on real NSE ATM weekly straddles 2020-2026:
# predicting the day's close from the day's open, pure trading-time over-decays (bias -1.6% of
# premium), pure calendar-time under-decays (+9.1%); 0.75 gives median +0.2% / mean -0.6%.
TIME_BLEND = 0.75


def trading_years_to_expiry(ts: pd.Timestamp, expiry_date: pd.Timestamp) -> float:
    """Remaining session minutes today + full sessions on weekdays in (today, expiry], / 252x375."""
    day = ts.normalize()
    exp = pd.Timestamp(expiry_date).normalize()
    if exp < day:
        return 0.0
    now_min = ts.hour * 60 + ts.minute
    today_left = min(max(SESSION_CLOSE_MIN - now_min, 0), SESSION_MINUTES)
    # busday_count counts weekdays in [day, exp) == weekdays in (day, exp] when both are weekdays
    later_days = int(np.busday_count(day.date(), exp.date()))
    mins = today_left + max(later_days, 0) * SESSION_MINUTES
    return mins / TRADING_MINUTES_PER_YEAR


def calendar_years_to_expiry(ts: pd.Timestamp, expiry_date: pd.Timestamp) -> float:
    mins = (pd.Timestamp(expiry_date).normalize() + EXPIRY_TIME - ts).total_seconds() / 60.0
    return max(mins, 0.0) / MINUTES_PER_YEAR


def years_to_expiry(ts: pd.Timestamp, expiry_date: pd.Timestamp, blend: float = None) -> float:
    """Blended trading/calendar time to expiry (see TIME_BLEND)."""
    w = TIME_BLEND if blend is None else blend
    return w * trading_years_to_expiry(ts, expiry_date) + (1.0 - w) * calendar_years_to_expiry(ts, expiry_date)


def dte_bucket(ts: pd.Timestamp, expiry_date: pd.Timestamp) -> int:
    return int(min(max((expiry_date.normalize() - ts.normalize()).days, 0), 7))


def moneyness_bucket(spot: float, strike: float) -> float:
    """(K - S)/S in percent, rounded to 0.5% and clipped to [-4, 4]."""
    m = (strike - spot) / spot * 100.0
    return float(min(max(round(m * 2.0) / 2.0, -4.0), 4.0))


@dataclass
class IVCalibration:
    """Multiplier on VIX/100 by (option type, DTE bucket, moneyness bucket)."""

    table: Dict[Tuple[str, int, float], float] = field(default_factory=dict)
    fallback: Dict[str, float] = field(default_factory=lambda: {"CE": 1.0, "PE": 1.0})
    stats: Dict[str, float] = field(default_factory=dict)

    def ratio(self, opt: str, dte: int, mny: float) -> float:
        r = self.table.get((opt, dte, mny))
        if r is None:
            r = self.fallback.get(opt, 1.0)
        return r

    def iv(self, vix: float, opt: str, ts: pd.Timestamp, expiry: pd.Timestamp, spot: float, strike: float) -> float:
        return max(vix / 100.0 * self.ratio(opt, dte_bucket(ts, expiry), moneyness_bucket(spot, strike)), 0.02)

    def to_dict(self) -> Dict[str, object]:
        return {
            "fallback": self.fallback,
            "stats": self.stats,
            "table": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in sorted(self.table.items())},
        }

    @classmethod
    def identity(cls) -> "IVCalibration":
        return cls()


def calibrate_from_real_options(
    options: pd.DataFrame,
    spot_5m: pd.DataFrame,
    vix_5m: pd.DataFrame,
    *,
    rate: float = 0.065,
    min_samples: int = 30,
    min_volume: float = 1000.0,
) -> IVCalibration:
    """
    Fit IV/VIX ratios from real daily option OPEN (vs 09:15 spot/VIX) and CLOSE (vs 15:25).

    ``options`` columns: date, expiry, strike, option_type, open, close, volume.
    ``spot_5m`` / ``vix_5m``: DatetimeIndex 5m bars with open/close.
    Only the nearest expiry per date is used (that is what the strategy trades).
    """
    o = options.copy()
    o["date"] = pd.to_datetime(o["date"]).dt.normalize()
    o["expiry"] = pd.to_datetime(o["expiry"]).dt.normalize()
    o = o[(o["expiry"] >= o["date"]) & (o["volume"].fillna(0) >= min_volume)]
    nearest = o.groupby("date")["expiry"].transform("min")
    o = o[o["expiry"] == nearest]

    def at(df: pd.DataFrame, hm: str, col: str) -> pd.Series:
        s = df[df.index.strftime("%H:%M") == hm][col]
        s.index = s.index.normalize()
        return s[~s.index.duplicated()]

    samples = []
    for hm, price_col, spot_col in (("09:15", "open", "open"), ("15:25", "close", "close")):
        spot = at(spot_5m, hm, spot_col).rename("spot")
        vix = at(vix_5m, hm, spot_col).rename("vix")
        df = o.join(spot, on="date").join(vix, on="date").dropna(subset=["spot", "vix", price_col])
        h, m = map(int, hm.split(":"))
        ts = df["date"] + pd.Timedelta(hours=h, minutes=m + (5 if hm == "15:25" else 0))
        keys = pd.DataFrame({"ts": ts, "expiry": df["expiry"]}).drop_duplicates()
        keys["t"] = [years_to_expiry(a, b) for a, b in zip(keys["ts"], keys["expiry"])]
        df = df.assign(ts=ts, price=df[price_col].astype(float)).merge(keys, on=["ts", "expiry"], how="left")
        df = df[(df["t"] > 30.0 / TRADING_MINUTES_PER_YEAR) & (df["price"] >= 2.0)]
        samples.append(df)
    s = pd.concat(samples, ignore_index=True)
    is_call = (s["option_type"] == "CE").to_numpy()
    s["iv"] = implied_vol_vec(s["price"], s["spot"], s["strike"], s["t"], rate, is_call)
    s = s.dropna(subset=["iv"])
    s["ratio"] = s["iv"] / (s["vix"] / 100.0)
    s = s[(s["ratio"] > 0.2) & (s["ratio"] < 5.0)]
    s["dte"] = (s["expiry"] - s["date"]).dt.days.clip(0, 7).astype(int)
    s["mny"] = (((s["strike"] - s["spot"]) / s["spot"] * 100.0 * 2.0).round() / 2.0).clip(-4.0, 4.0)

    cal = IVCalibration()
    for opt in ("CE", "PE"):
        sub = s[s["option_type"] == opt]
        if len(sub):
            cal.fallback[opt] = float(sub["ratio"].median())
    grouped = s.groupby(["option_type", "dte", "mny"])["ratio"]
    med, cnt = grouped.median(), grouped.size()
    for key, r in med.items():
        if cnt[key] >= min_samples:
            cal.table[(key[0], int(key[1]), float(key[2]))] = float(r)

    # In-sample fit quality: abs % error of re-priced ATM-ish samples
    atm = s[s["mny"].abs() <= 1.0].copy()
    if len(atm):
        ratios = np.array([cal.ratio(o_, int(d), float(m)) for o_, d, m in zip(atm["option_type"], atm["dte"], atm["mny"])])
        model = bs_price_vec(atm["spot"], atm["strike"], atm["t"], atm["vix"] / 100.0 * ratios, rate,
                             (atm["option_type"] == "CE").to_numpy())
        err = np.abs(model - atm["price"].to_numpy()) / atm["price"].to_numpy()
        cal.stats = {
            "samples": float(len(s)),
            "atm_samples": float(len(atm)),
            "atm_median_abs_pct_err": float(np.median(err) * 100.0),
            "atm_p90_abs_pct_err": float(np.percentile(err, 90) * 100.0),
            "date_min": str(s["date"].min().date()),
            "date_max": str(s["date"].max().date()),
        }
    return cal
