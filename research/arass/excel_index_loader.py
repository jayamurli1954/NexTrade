"""Load Nifty / BankNifty / India VIX daily OHLC from the user's Excel workbook."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from research.arass.data_loader import _normalize_ohlcv, expand_daily_to_intraday

# Default path from user's Downloads (override via CLI)
DEFAULT_INDEX_EXCEL = Path(r"D:\Download\Historical Data_Nifty50-BankNifty_IndiaVix.xlsx")

SHEET_MAP = {
    "NIFTY": "Nifty50_Historical_Data",
    "BANKNIFTY": "Historical Data_Nifty50-BankNif",
    "INDIAVIX": "India_Vix_Historical_Data",
}


def load_excel_sheet_ohlcv(path: Path | str, sheet: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Index Excel not found: {path}")
    df = pd.read_excel(path, sheet_name=sheet)
    if "Date" not in df.columns:
        raise ValueError(f"Sheet {sheet} missing Date column; got {list(df.columns)}")
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return _normalize_ohlcv(df)


def load_index_workbook(
    path: Path | str = DEFAULT_INDEX_EXCEL,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """Return daily OHLCV frames keyed NIFTY / BANKNIFTY / INDIAVIX."""
    path = Path(path)
    out: Dict[str, pd.DataFrame] = {}
    for key, sheet in SHEET_MAP.items():
        df = load_excel_sheet_ohlcv(path, sheet)
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        out[key] = df
    return out


def export_index_csvs(
    path: Path | str = DEFAULT_INDEX_EXCEL,
    out_dir: Optional[Path | str] = None,
) -> Dict[str, Path]:
    """Write cleaned daily CSVs under research/data/indices/."""
    root = Path(__file__).resolve().parents[2]
    out_dir = Path(out_dir) if out_dir else root / "research" / "data" / "indices"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = load_index_workbook(path)
    written: Dict[str, Path] = {}
    for key, df in frames.items():
        dest = out_dir / f"{key.lower()}_daily.csv"
        df.to_csv(dest)
        written[key] = dest
    return written


def load_arass_panel_from_excel(
    *,
    symbol: str = "NIFTY",
    excel_path: Path | str = DEFAULT_INDEX_EXCEL,
    start: str = "2016-01-01",
    end: str = "2026-08-01",
    expand_intraday: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """
    Build ARASS panel (spot + vix) from the local Excel workbook.
    """
    frames = load_index_workbook(excel_path, start=start, end=end)
    key = symbol.upper()
    if key not in frames:
        raise KeyError(f"Unknown symbol {symbol}; expected NIFTY or BANKNIFTY")
    spot_daily = frames[key]
    vix_daily = frames["INDIAVIX"]
    if expand_intraday:
        from research.arass.data_loader import align_vix_to_index

        spot = expand_daily_to_intraday(spot_daily, bar_minutes=5)
        panel = spot.copy()
        panel["vix"] = align_vix_to_index(panel, vix_daily)
        provenance = f"excel_daily_expanded:{Path(excel_path).name}|{key}|INDIAVIX"
    else:
        panel = spot_daily.copy()
        v = vix_daily["close"].copy()
        v.index = pd.to_datetime(v.index).normalize()
        panel["vix"] = panel.index.normalize().map(v).ffill().bfill()
        provenance = f"excel_daily:{Path(excel_path).name}|{key}|INDIAVIX"
    panel = panel.dropna(subset=["close", "vix"])
    return panel, provenance
