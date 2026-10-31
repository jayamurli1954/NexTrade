"""
Technical feature computation for Feature Store (B1c).

Research-only. Uses local OHLC cache + yfinance for NSE equities.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from indicators.ta import ema, rsi
from research.arass.indicators import adx, atr

logger = logging.getLogger("TechnicalFeatures")


def load_feature_config(path: Optional[Path] = None) -> Dict[str, Any]:
    cfg_path = path or (Path(__file__).resolve().parents[1] / "config" / "feature_store.json")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def load_watchlist(path: Optional[Path] = None) -> List[str]:
    p = path or (Path(__file__).resolve().parents[1] / "watchlist.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(s).upper().strip() for s in data]
    return [str(s).upper().strip() for s in (data.get("symbols") or [])]


def _yf_ticker(symbol: str) -> str:
    from research.fundamentals_aliases import resolve_fetch_symbol

    s = resolve_fetch_symbol(symbol.upper().strip())
    if s in ("NIFTY", "NIFTY50"):
        return "^NSEI"
    if s in ("BANKNIFTY",):
        return "^NSEBANK"
    if s in ("INDIAVIX", "INDIA_VIX", "VIX"):
        return "^INDIAVIX"
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def ohlc_cache_dir(feature_root: Path) -> Path:
    d = feature_root / "ohlc_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_or_download_daily_ohlc(
    symbol: str,
    *,
    start: str,
    end: str,
    cache_dir: Path,
    sleep_s: float = 0.35,
    force: bool = False,
) -> pd.DataFrame:
    """
    Return daily OHLCV indexed by date (tz-naive). Cache as CSV under ohlc_cache.
    """
    cache_path = cache_dir / f"{symbol.upper()}.csv"
    if cache_path.exists() and not force:
        df = pd.read_csv(cache_path, parse_dates=["date"])
        df = df.set_index("date").sort_index()
        # refresh if cache ends before requested end by > 5 days
        end_ts = pd.Timestamp(end)
        if len(df) and df.index.max() >= end_ts - pd.Timedelta(days=5):
            return df

    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance required for B1c technical backfill") from e

    yf_sym = _yf_ticker(symbol)
    time.sleep(max(0.0, sleep_s))
    raw = yf.Ticker(yf_sym).history(start=start, end=end, interval="1d", auto_adjust=True)
    if raw is None or raw.empty:
        logger.warning("No OHLC for %s (%s)", symbol, yf_sym)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    out = raw.rename(columns={c: c.lower() for c in raw.columns})
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in out.columns]
    out = out[keep].copy()
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.index.name = "date"
    save = out.reset_index()
    save["date"] = pd.to_datetime(save["date"]).dt.strftime("%Y-%m-%d")
    save.to_csv(cache_path, index=False)
    return out


def compute_technical_frame(
    ohlc: pd.DataFrame,
    *,
    rsi_period: int = 14,
    ema_short: int = 20,
    ema_long: int = 50,
    atr_period: int = 14,
    adx_period: int = 14,
) -> pd.DataFrame:
    if ohlc is None or ohlc.empty:
        return pd.DataFrame(columns=["rsi", "ema20", "ema50", "atr", "adx"])
    close = ohlc["close"]
    high = ohlc["high"]
    low = ohlc["low"]
    frame = pd.DataFrame(index=ohlc.index)
    frame["rsi"] = rsi(close, rsi_period)
    frame["ema20"] = ema(close, ema_short)
    frame["ema50"] = ema(close, ema_long)
    frame["atr"] = atr(high, low, close, atr_period)
    frame["adx"] = adx(high, low, close, adx_period)
    return frame


def build_technical_rows_for_symbol(
    symbol: str,
    tech: pd.DataFrame,
    *,
    vix_by_date: Optional[Dict[str, float]] = None,
    start_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if tech is None or tech.empty:
        return rows
    for dt, row in tech.iterrows():
        d = pd.Timestamp(dt).strftime("%Y-%m-%d")
        if start_date and d < start_date:
            continue
        if pd.isna(row.get("rsi")) and pd.isna(row.get("ema20")):
            continue
        rec = {
            "date": d,
            "symbol": symbol.upper(),
            "rsi": None if pd.isna(row.get("rsi")) else round(float(row["rsi"]), 4),
            "ema20": None if pd.isna(row.get("ema20")) else round(float(row["ema20"]), 4),
            "ema50": None if pd.isna(row.get("ema50")) else round(float(row["ema50"]), 4),
            "atr": None if pd.isna(row.get("atr")) else round(float(row["atr"]), 4),
            "adx": None if pd.isna(row.get("adx")) else round(float(row["adx"]), 4),
            "vix": None,
            "pcr": None,
            "oi": None,
        }
        if vix_by_date is not None:
            rec["vix"] = vix_by_date.get(d)
        rows.append(rec)
    return rows


def load_vix_series(
    *,
    start: str,
    end: str,
    cache_dir: Path,
    sleep_s: float = 0.35,
) -> Dict[str, float]:
    df = load_or_download_daily_ohlc("INDIAVIX", start=start, end=end, cache_dir=cache_dir, sleep_s=sleep_s)
    out: Dict[str, float] = {}
    for dt, row in df.iterrows():
        d = pd.Timestamp(dt).strftime("%Y-%m-%d")
        try:
            out[d] = round(float(row["close"]), 4)
        except (TypeError, ValueError):
            continue
    return out
