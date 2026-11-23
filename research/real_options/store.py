"""
Compact per-day store of real 1-minute index-option prices (nearest expiry) + spot.

Source: Kaggle archive with ``{und}_data/{und}_options/YYYY/M/{und}_options_DD_MM_YYYY.csv`` (1-minute OHLC
for every strike of the nearest expiry) and ``{und}_spot/.../{und}_spotDD_MM_YYYY.csv``. Each trading day becomes
``research/data/real_options/{und}/{YYYY-MM-DD}.npz`` holding a 375-minute grid (09:15..15:29):

  spot_ohlc  float32 [375, 4]
  strikes    float64 [n]        option_type uint8 [n] (0=CE, 1=PE)
  ohlc       float32 [n, 375, 4] (no-trade minutes carry the previous close; NaN before the first trade)
  expiry     str 'YYYY-MM-DD'

Strikes outside +/- ``WINDOW_PCT`` of the day's opening spot are dropped (deep ITM/OTM, never traded here).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STORE_DIR = ROOT / "research" / "data" / "real_options"
N_MIN = 375                      # 09:15 .. 15:29
WINDOW_PCT = 12.0
_SYM = re.compile(r"^[A-Z]+(\d{2}[A-Z]{3}\d{2})(\d+(?:\.\d+)?)(CE|PE)$")


def minute_index(times: pd.Series) -> np.ndarray:
    """'09:15:00' / '9:15' / '2023-06-06 09:15:00' -> minutes since 09:15; unparseable -> -1 (dropped)."""
    hm = times.astype(str).str.extract(r"(\d{1,2}):(\d{2})")
    h = pd.to_numeric(hm[0], errors="coerce")
    m = pd.to_numeric(hm[1], errors="coerce")
    mins = (h * 60 + m - (9 * 60 + 15)).fillna(-1).astype(int)
    return mins.to_numpy()


def _grid_ohlc(idx: np.ndarray, ohlc: np.ndarray) -> np.ndarray:
    """Place bars on the 375-minute grid; carry the previous close through no-trade minutes."""
    out = np.full((N_MIN, 4), np.nan, dtype=np.float32)
    ok = (idx >= 0) & (idx < N_MIN)
    out[idx[ok]] = ohlc[ok]
    last = np.nan
    for i in range(N_MIN):
        if np.isnan(out[i, 3]):
            if not np.isnan(last):
                out[i] = last
        else:
            last = out[i, 3]
    return out


def convert_day(opt_csv: bytes, spot_csv: bytes) -> Optional[dict]:
    spot = pd.read_csv(io.BytesIO(spot_csv), usecols=["time", "open", "high", "low", "close"])
    sidx = minute_index(spot["time"].astype(str))
    spot_grid = _grid_ohlc(sidx, spot[["open", "high", "low", "close"]].to_numpy(np.float32))
    if np.isnan(spot_grid[0, 0]):
        first = np.flatnonzero(~np.isnan(spot_grid[:, 0]))
        if not len(first):
            return None
        spot_grid[: first[0]] = spot_grid[first[0]]
    s0 = float(spot_grid[0, 0])

    o = pd.read_csv(io.BytesIO(opt_csv), usecols=["time", "symbol", "open", "high", "low", "close"])
    parts = o["symbol"].astype(str).str.extract(_SYM)
    o = o.assign(exp=parts[0], strike=pd.to_numeric(parts[1], errors="coerce"), ot=parts[2]).dropna(subset=["strike", "ot"])
    o = o[(o["strike"] - s0).abs() / s0 * 100.0 <= WINDOW_PCT]
    if o.empty:
        return None
    expiry = datetime.strptime(o["exp"].mode().iloc[0], "%d%b%y").date().isoformat()
    o["mi"] = minute_index(o["time"].astype(str))
    keys, arrays = [], []
    for (k, ot), g in o.groupby(["strike", "ot"], sort=True):
        keys.append((k, 0 if ot == "CE" else 1))
        arrays.append(_grid_ohlc(g["mi"].to_numpy(), g[["open", "high", "low", "close"]].to_numpy(np.float32)))
    return {
        "spot_ohlc": spot_grid,
        "strikes": np.array([k for k, _ in keys], dtype=np.float64),
        "option_type": np.array([t for _, t in keys], dtype=np.uint8),
        "ohlc": np.stack(arrays).astype(np.float32),
        "expiry": np.array(expiry),
    }


def convert_archive(zip_path: Path, underlying: str, out_dir: Path = STORE_DIR, overwrite: bool = False) -> Tuple[int, int]:
    und = underlying.lower()
    z = zipfile.ZipFile(zip_path)
    names = z.namelist()
    spot_by_day = {}
    for n in names:
        m = re.search(rf"{und}_data/{und}_spot/.*?(\d{{2}})_(\d{{2}})_(\d{{4}})\.csv$", n)
        if m:
            spot_by_day[f"{m.group(3)}-{m.group(2)}-{m.group(1)}"] = n
    out = out_dir / und
    out.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    for n in sorted(names):
        m = re.search(rf"{und}_data/{und}_options/.*?(\d{{2}})_(\d{{2}})_(\d{{4}})\.csv$", n)
        if not m:
            continue
        day = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        target = out / f"{day}.npz"
        if (target.exists() and not overwrite) or day not in spot_by_day:
            skipped += 1
            continue
        rec = convert_day(z.read(n), z.read(spot_by_day[day]))
        if rec is None:
            skipped += 1
            continue
        np.savez_compressed(target, **rec)
        done += 1
    return done, skipped


@dataclass
class DayData:
    day: date
    expiry: date
    spot: np.ndarray            # [375, 4]
    strikes: np.ndarray
    option_type: np.ndarray     # 0=CE 1=PE
    ohlc: np.ndarray            # [n, 375, 4]

    def __post_init__(self):
        self._index: Dict[Tuple[float, int], int] = {(float(k), int(t)): i for i, (k, t) in
                                                      enumerate(zip(self.strikes, self.option_type))}

    def series(self, strike: float, opt: str) -> Optional[np.ndarray]:
        i = self._index.get((float(strike), 0 if opt == "CE" else 1))
        return None if i is None else self.ohlc[i]

    def available(self, opt: str) -> np.ndarray:
        t = 0 if opt == "CE" else 1
        return np.sort(self.strikes[self.option_type == t])


def load_day(underlying: str, day: str, store: Path = STORE_DIR) -> Optional[DayData]:
    path = store / underlying.lower() / f"{day}.npz"
    if not path.exists():
        return None
    z = np.load(path)
    return DayData(date.fromisoformat(day), date.fromisoformat(str(z["expiry"])), z["spot_ohlc"],
                   z["strikes"], z["option_type"], z["ohlc"])


def iter_days(underlying: str, start: Optional[str] = None, end: Optional[str] = None,
              store: Path = STORE_DIR) -> Iterator[DayData]:
    for path in sorted((store / underlying.lower()).glob("*.npz")):
        d = path.stem
        if (start and d < start) or (end and d > end):
            continue
        dd = load_day(underlying, d, store)
        if dd is not None:
            yield dd


if __name__ == "__main__":
    import argparse
    import time

    ap = argparse.ArgumentParser(description="Convert the Kaggle 1-minute options archive into the npz store")
    ap.add_argument("--zip", required=True)
    ap.add_argument("--underlying", required=True, choices=["banknifty", "nifty"])
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    done, skipped = convert_archive(Path(a.zip), a.underlying, overwrite=a.overwrite)
    print(f"{a.underlying}: converted {done}, skipped {skipped} in {time.time() - t0:.0f}s -> {STORE_DIR / a.underlying}")
