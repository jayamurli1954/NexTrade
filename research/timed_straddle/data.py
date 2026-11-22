"""Data loading for the timed-straddle backtest: 5m index + India VIX, real options, expiry calendar."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
KAGGLE_DIR = ROOT / "research" / "data" / "intraday" / "kaggle_nifty100_5m"
OPTIONS_CSV = ROOT / "research" / "data" / "options" / "nifty_options_daily.csv"

INDEX_FILES = {"NIFTY": "NIFTY 50_5minute.csv", "BANKNIFTY": "NIFTY BANK_5minute.csv", "INDIAVIX": "INDIA VIX_5minute.csv"}

# BANKNIFTY weekly expiries were discontinued by NSE after 2024-11-20.
BANKNIFTY_WEEKLY_END = pd.Timestamp("2024-11-20")
BANKNIFTY_WED_START = pd.Timestamp("2023-09-04")  # weekly expiry moved Thursday -> Wednesday


def load_5m(name: str, data_dir: Path = KAGGLE_DIR) -> pd.DataFrame:
    """Load a Kaggle 5m CSV, keeping regular-session bars 09:15..15:25."""
    df = pd.read_csv(data_dir / INDEX_FILES[name], parse_dates=["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    hm = df.index.strftime("%H:%M")
    df = df[(hm >= "09:15") & (hm <= "15:25")]
    return df[["open", "high", "low", "close"]].astype(float)


def build_panel(symbol: str, start: Optional[str] = None, end: Optional[str] = None,
                data_dir: Path = KAGGLE_DIR) -> pd.DataFrame:
    """Index OHLC with aligned VIX close (as-of, forward-filled within the day)."""
    spot = load_5m(symbol, data_dir)
    vix = load_5m("INDIAVIX", data_dir)
    if start:
        spot = spot[spot.index >= pd.Timestamp(start)]
    if end:
        spot = spot[spot.index < pd.Timestamp(end) + pd.Timedelta(days=1)]
    vix_close = vix["close"].reindex(spot.index)
    vix_close = vix_close.groupby(spot.index.normalize()).ffill().bfill()
    panel = spot.assign(vix=vix_close).dropna()
    return panel


def load_real_options(path: Path = OPTIONS_CSV) -> pd.DataFrame:
    cols = ["date", "expiry", "strike", "option_type", "open", "high", "low", "close", "volume"]
    return pd.read_csv(path, usecols=cols, parse_dates=["date", "expiry"])


def _shift_to_trading_day(day: pd.Timestamp, trading_days: pd.DatetimeIndex) -> Optional[pd.Timestamp]:
    """Holiday rule: if the expiry weekday is not a trading day, expire on the previous one."""
    pos = trading_days.searchsorted(day, side="right") - 1
    if pos < 0:
        return None
    d = trading_days[pos]
    return d if (day - d).days < 7 else None


def build_expiry_calendar(symbol: str, trading_days: Iterable[pd.Timestamp],
                          real_expiries: Optional[Iterable[pd.Timestamp]] = None) -> Dict[pd.Timestamp, pd.Timestamp]:
    """
    Map each trading day -> nearest weekly expiry (on or after that day).

    NIFTY: real expiry dates from the NSE options file where available (captures the 2025
    Thursday->Tuesday switch and holiday shifts); weekly-Thursday rule before that.
    BANKNIFTY: Thursday rule, Wednesday from 2023-09-04, no weeklies after 2024-11-20.
    """
    days = pd.DatetimeIndex(sorted(pd.Timestamp(d).normalize() for d in trading_days)).unique()
    expiries: List[pd.Timestamp] = []
    real = sorted({pd.Timestamp(e).normalize() for e in (real_expiries or [])}) if symbol == "NIFTY" else []
    real_start = real[0] if real else None

    # Rule-based weekly expiries
    week_starts = pd.date_range(days[0] - pd.Timedelta(days=7), days[-1] + pd.Timedelta(days=14), freq="W-MON")
    for ws in week_starts:
        if symbol == "BANKNIFTY" and ws >= BANKNIFTY_WED_START:
            wd = 2
        else:
            wd = 3
        nominal = ws + pd.Timedelta(days=wd)
        if real_start is not None and nominal >= real_start:
            continue
        if symbol == "BANKNIFTY" and nominal > BANKNIFTY_WEEKLY_END:
            continue
        e = _shift_to_trading_day(nominal, days)
        if e is not None:
            expiries.append(e)
    expiries.extend(real)
    exp_idx = pd.DatetimeIndex(sorted(set(expiries)))

    out: Dict[pd.Timestamp, pd.Timestamp] = {}
    for d in days:
        pos = exp_idx.searchsorted(d, side="left")
        if pos < len(exp_idx) and (exp_idx[pos] - d).days <= 7:
            out[d] = exp_idx[pos]
    return out
