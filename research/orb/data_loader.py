"""Load Kaggle NSE 5m CSVs for ORB research."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger("OrbDataLoader")

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "intraday" / "kaggle_nifty100_5m"
NIFTY_FILE = "NIFTY 50_5minute.csv"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def list_symbol_files(data_dir: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for p in sorted(data_dir.glob("*_5minute.csv")):
        name = p.name[: -len("_5minute.csv")]
        if name in {"NIFTY 50", "NIFTY BANK", "INDIA VIX"}:
            continue
        out[name] = p
    return out


def resolve_symbols(
    data_dir: Path,
    *,
    symbols: Optional[Sequence[str]] = None,
    use_watchlist: bool = True,
    max_symbols: Optional[int] = None,
) -> List[str]:
    files = {p.name[: -len("_5minute.csv")]: p for p in data_dir.glob("*_5minute.csv")}
    # drop indices from trade universe
    for drop in ("NIFTY 50", "NIFTY BANK", "INDIA VIX"):
        files.pop(drop, None)

    if symbols:
        wanted = [s.strip().upper() for s in symbols if s.strip()]
    elif use_watchlist:
        wl_path = _repo_root() / "watchlist.json"
        wanted = [str(s).upper() for s in json.loads(wl_path.read_text(encoding="utf-8"))]
    else:
        wanted = sorted(files.keys())

    # map watchlist names to file names (BAJAJ-AUTO etc.)
    file_upper = {k.upper(): k for k in files}
    # also allow hyphenless match
    hyphen_map = {k.upper().replace("-", ""): k for k in files}

    resolved: List[str] = []
    missing: List[str] = []
    for s in wanted:
        key = s.upper()
        if key in file_upper:
            resolved.append(file_upper[key])
        elif key.replace("-", "") in hyphen_map:
            resolved.append(hyphen_map[key.replace("-", "")])
        else:
            missing.append(s)
    if missing:
        logger.info("ORB symbols missing from Kaggle set (%d): %s", len(missing), ", ".join(missing[:12]))
    if max_symbols is not None:
        resolved = resolved[: int(max_symbols)]
    return resolved


def load_ohlcv_csv(path: Path, *, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError(f"missing date column: {path}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        if c not in df.columns:
            raise ValueError(f"missing {c} in {path}")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        # inclusive calendar end of day
        df = df[df.index <= pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59)]
    return df


def load_nifty_panel(data_dir: Path, *, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    path = data_dir / NIFTY_FILE
    if not path.exists():
        raise FileNotFoundError(f"Nifty 50 5m file not found: {path}")
    return load_ohlcv_csv(path, start=start, end=end)


def load_symbol_panels(
    data_dir: Path,
    symbols: Sequence[str],
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    files = {p.name[: -len("_5minute.csv")]: p for p in data_dir.glob("*_5minute.csv")}
    panels: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        path = files.get(sym)
        if path is None:
            continue
        df = load_ohlcv_csv(path, start=start, end=end)
        if not df.empty:
            panels[sym] = df
    return panels


def default_data_dir() -> Path:
    return DEFAULT_DATA_DIR
