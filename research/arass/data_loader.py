"""Load NIFTY/BANKNIFTY + India VIX for ARASS research.

Modes:
- yfinance daily (multi-year) expanded to coarse intraday path
- yfinance 5m (recent ~60d) when available
- local CSV override for spot / vix / options OHLC
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("ArassDataLoader")

YF_SYMBOLS = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "INDIAVIX": "^INDIAVIX",
}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    mapping = {}
    for need in ("open", "high", "low", "close", "volume"):
        if need in cols:
            mapping[cols[need]] = need
        elif need.title() in df.columns:
            mapping[need.title()] = need
    out = df.rename(columns=mapping)
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in out.columns]
    out = out[keep].copy()
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_convert("Asia/Kolkata").tz_localize(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.dropna(subset=["open", "high", "low", "close"])


def load_yfinance_daily(symbol_key: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    yf_sym = YF_SYMBOLS.get(symbol_key.upper(), symbol_key)
    raw = yf.Ticker(yf_sym).history(start=start, end=end, interval="1d", auto_adjust=True)
    if raw is None or raw.empty:
        raise RuntimeError(f"No yfinance daily data for {yf_sym}")
    return _normalize_ohlcv(raw)


def load_yfinance_5m(symbol_key: str, period: str = "60d") -> pd.DataFrame:
    import yfinance as yf

    yf_sym = YF_SYMBOLS.get(symbol_key.upper(), symbol_key)
    raw = yf.Ticker(yf_sym).history(period=period, interval="5m", auto_adjust=True)
    if raw is None or raw.empty:
        raise RuntimeError(f"No yfinance 5m data for {yf_sym}")
    return _normalize_ohlcv(raw)


def load_csv_ohlcv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path)
    for cand in ("datetime", "Datetime", "date", "Date", "timestamp", "Timestamp"):
        if cand in df.columns:
            df[cand] = pd.to_datetime(df[cand])
            df = df.set_index(cand)
            break
    return _normalize_ohlcv(df)


def expand_daily_to_intraday(daily: pd.DataFrame, bar_minutes: int = 5) -> pd.DataFrame:
    """
    Expand daily OHLC into a coarse NSE session path (09:15-15:30).

    Morning (until ~10:45) stays near the open so OR/VWAP filters are meaningful.
    High/low extremes are visited after the ARASS entry window.
    Research approximation only — replace with real 5m when available.
    """
    rows = []
    start_min = 9 * 60 + 15
    session_end_min = 15 * 60 + 30
    n_bars = (session_end_min - start_min) // bar_minutes
    entry_cut = ((10 * 60 + 45) - start_min) // bar_minutes

    for ts, row in daily.iterrows():
        day = pd.Timestamp(ts).normalize()
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        vol = float(row.get("volume", 0.0) or 0.0)
        morning_end = o + 0.25 * (c - o)
        path = np.zeros(n_bars, dtype=float)
        for i in range(n_bars):
            if i <= entry_cut:
                frac = i / max(entry_cut, 1)
                path[i] = o + (morning_end - o) * frac
            else:
                frac = (i - entry_cut) / max(n_bars - 1 - entry_cut, 1)
                # Afternoon: drift open->close; embed a single adverse excursion mid-afternoon
                # (half the day range toward the farther extreme) then revert toward close.
                mid = entry_cut + (n_bars - 1 - entry_cut) // 2
                adverse = h if abs(h - o) >= abs(l - o) else l
                if i <= mid:
                    local = (i - entry_cut) / max(mid - entry_cut, 1)
                    path[i] = morning_end + (adverse - morning_end) * local * 0.5
                else:
                    local = (i - mid) / max(n_bars - 1 - mid, 1)
                    path[i] = path[mid] + (c - path[mid]) * local
        for i, px in enumerate(path):
            minute = start_min + i * bar_minutes
            t = day + pd.Timedelta(hours=minute // 60, minutes=minute % 60)
            prev = path[i - 1] if i else px
            # Keep bar range local; attach true day H/L only as soft envelope via clip
            hi = max(prev, px)
            lo = min(prev, px)
            rows.append(
                {
                    "datetime": t,
                    "open": float(prev),
                    "high": float(hi),
                    "low": float(lo),
                    "close": float(px),
                    "volume": vol / max(n_bars, 1),
                }
            )
    return pd.DataFrame(rows).set_index("datetime")


def align_vix_to_index(index_df: pd.DataFrame, vix_daily: pd.DataFrame) -> pd.Series:
    """Forward-fill daily VIX onto intraday index bars."""
    v = vix_daily["close"].copy()
    v.index = pd.to_datetime(v.index).normalize()
    days = pd.Series(index_df.index.normalize(), index=index_df.index)
    mapped = days.map(v)
    return mapped.ffill().bfill()


def load_arass_market_panel(
    *,
    symbol: str = "NIFTY",
    start: str = "2016-01-01",
    end: str = "2026-08-01",
    mode: str = "daily_expanded",
    spot_csv: Optional[str] = None,
    vix_csv: Optional[str] = None,
    excel_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, str]:
    """
    Returns (panel, data_provenance_note).
    Panel columns: open,high,low,close,volume,vix

    mode:
      - daily_expanded: yfinance daily → coarse 5m path (default)
      - 5m: yfinance 5m (short history)
      - excel: local Nifty/BankNifty/VIX workbook (see excel_index_loader)
    """
    if excel_path or mode == "excel":
        from research.arass.excel_index_loader import DEFAULT_INDEX_EXCEL, load_arass_panel_from_excel

        path = excel_path or str(DEFAULT_INDEX_EXCEL)
        panel, provenance = load_arass_panel_from_excel(
            symbol=symbol,
            excel_path=path,
            start=start,
            end=end,
            expand_intraday=True,
        )
        logger.info("ARASS panel rows=%s provenance=%s", len(panel), provenance)
        return panel, provenance

    if spot_csv:
        spot = load_csv_ohlcv(spot_csv)
        provenance = f"spot_csv:{spot_csv}"
    elif mode == "5m":
        spot = load_yfinance_5m(symbol)
        provenance = f"yfinance_5m:{YF_SYMBOLS.get(symbol, symbol)}"
    else:
        daily = load_yfinance_daily(symbol, start, end)
        spot = expand_daily_to_intraday(daily, bar_minutes=5)
        provenance = f"yfinance_daily_expanded:{YF_SYMBOLS.get(symbol, symbol)}"

    if vix_csv:
        vix = load_csv_ohlcv(vix_csv)
        provenance += f"|vix_csv:{vix_csv}"
    else:
        vix = load_yfinance_daily("INDIAVIX", start, end)
        provenance += "|yfinance_vix_daily"

    panel = spot.copy()
    panel["vix"] = align_vix_to_index(panel, vix)
    panel = panel.dropna(subset=["close", "vix"])
    logger.info("ARASS panel rows=%s provenance=%s", len(panel), provenance)
    return panel, provenance
