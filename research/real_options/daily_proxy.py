"""
Daily-price proxy backtest for short straddles/strangles, for periods where only daily option OHLC exists
(NSE bhavcopy, Nov 2024 onward — the BANKNIFTY monthly-only era).

Rules that daily bars can represent without knowing the intraday order of highs and lows:
  * enter at the day's OPEN (sell = open - slippage), strikes from the index open;
  * each short leg independent (no stop-to-cost, no re-entry): if the day's HIGH >= entry x (1 + SL%),
    the leg is stopped at the stop price + slippage, otherwise it is bought back at the CLOSE + slippage.
The stop check uses the whole day's high (including minutes before a 09:20/09:30 entry), so it is slightly
pessimistic. ``validate_against_minutes`` measures the proxy's bias against the 1-minute engine on 2020-2024.
"""

from __future__ import annotations

import glob
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from research.timed_straddle.costs import fill_cost

ROOT = Path(__file__).resolve().parents[2]
BHAV_DIR = ROOT / "research" / "data" / "options" / "nse_bhavcopy"
STEP = {"NIFTY": 50.0, "BANKNIFTY": 100.0}


@dataclass
class DailyChain:
    day: date
    expiry: date
    spot_open: float
    chain: pd.DataFrame   # columns: strike, option_type, open, high, low, close


@dataclass(frozen=True)
class ProxyParams:
    symbol: str = "BANKNIFTY"
    sl_pct: Optional[float] = 35.0     # None = no stop (hold to close)
    points_from_atm: float = 0.0
    slippage: float = 1.5
    lot_size: int = 30
    lots: int = 1
    brokerage: float = 20.0

    @property
    def qty(self) -> int:
        return self.lots * self.lot_size


# ---------------------------------------------------------------- data sources
def daily_from_minute_store(underlying: str, start: str = None, end: str = None) -> Iterator[DailyChain]:
    """Collapse the 1-minute real store to daily OHLC per contract (for validating the proxy)."""
    from research.real_options.store import iter_days

    for d in iter_days(underlying.lower(), start, end):
        o = d.ohlc
        first_open = np.array([s[np.flatnonzero(~np.isnan(s[:, 0]))[0], 0] if (~np.isnan(s[:, 0])).any() else np.nan
                               for s in o])
        df = pd.DataFrame({
            "strike": d.strikes, "option_type": np.where(d.option_type == 0, "CE", "PE"),
            "open": first_open, "high": np.nanmax(o[:, :, 1], axis=1), "low": np.nanmin(o[:, :, 2], axis=1),
            "close": o[:, -1, 3],
        }).dropna()
        yield DailyChain(d.day, d.expiry, float(d.spot[0, 0]), df)


def load_bhavcopy(underlying: str, bhav_dir: Path = BHAV_DIR) -> pd.DataFrame:
    files = sorted(glob.glob(str(bhav_dir / f"{underlying.lower()}_options_daily_*.csv")))
    if not files:
        return pd.DataFrame()
    df = pd.concat(pd.read_csv(f) for f in files)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    return df.drop_duplicates(["date", "expiry", "strike", "option_type"])


def daily_from_bhavcopy(underlying: str, spot_open: pd.Series, start: str = None, end: str = None,
                        bhav: Optional[pd.DataFrame] = None) -> Iterator[DailyChain]:
    """Nearest expiry (>= day) per trading day from the NSE bhavcopy store; spot_open indexed by date."""
    df = load_bhavcopy(underlying) if bhav is None else bhav
    if df.empty:
        return
    so = {pd.Timestamp(k).date(): float(v) for k, v in spot_open.items()}
    for day, g in df.groupby("date"):
        if (start and str(day) < start) or (end and str(day) > end):
            continue
        g = g[g["expiry"] >= day]
        if g.empty or day not in so:
            continue
        exp = g["expiry"].min()
        ch = g[(g["expiry"] == exp) & (g["volume"] > 0) & (g["open"] > 0)]
        yield DailyChain(day, exp, so[day], ch[["strike", "option_type", "open", "high", "low", "close"]].copy())


# ---------------------------------------------------------------- strategy
def run_proxy_straddle(days: Iterable[DailyChain], p: ProxyParams) -> pd.DataFrame:
    rows = []
    step = STEP[p.symbol]
    for d in days:
        atm = round(d.spot_open / step) * step
        legs = []
        for opt, k in (("CE", atm + p.points_from_atm), ("PE", atm - p.points_from_atm)):
            r = d.chain[(d.chain["strike"] == k) & (d.chain["option_type"] == opt)]
            if r.empty:
                legs = None
                break
            legs.append((opt, k, r.iloc[0]))
        if not legs:
            continue
        gross = costs = credit = 0.0
        why = []
        for opt, k, r in legs:
            entry = max(float(r["open"]) - p.slippage, 0.05)
            costs += fill_cost(entry, p.qty, "SELL", p.brokerage)
            credit += entry
            if p.sl_pct is not None and float(r["high"]) >= entry * (1 + p.sl_pct / 100.0):
                exitp = entry * (1 + p.sl_pct / 100.0) + p.slippage
                why.append("sl")
            else:
                exitp = float(r["close"]) + p.slippage
                why.append("close")
            costs += fill_cost(exitp, p.qty, "BUY", p.brokerage)
            gross += entry - exitp
        rows.append({"date": pd.Timestamp(d.day), "expiry": pd.Timestamp(d.expiry), "dte": (d.expiry - d.day).days,
                     "atm": atm, "entry_premium": credit, "gross_points": gross, "costs": costs,
                     "pnl": gross * p.qty - costs, "exit_reason": "+".join(why), "vix_entry": np.nan})
    return pd.DataFrame(rows)
