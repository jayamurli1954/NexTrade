#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Download NSE F&O daily bhavcopies (UDiFF format, Jul-2024 onward) and keep only index-option rows.

One request per trading day (``BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip`` from nsearchives),
filtered to the requested underlyings' index options (FinInstrmTp == IDO) and appended to
``research/data/options/nse_bhavcopy/<symbol>_options_daily_<year>.csv``. Raw zips are not kept.
Resume-safe via a manifest of finished days; holidays (HTTP 404) are recorded and skipped.

Research data only. Examples:
  python -m research.download_nse_fo_bhavcopy --start 2024-12-01 --end 2026-11-23
  python -m research.download_nse_fo_bhavcopy --start 2024-12-24 --end 2024-12-24 --symbols BANKNIFTY
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nse_fo_bhavcopy")

URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "*/*",
           "Referer": "https://www.nseindia.com/"}
OUT_DIR = ROOT / "research" / "data" / "options" / "nse_bhavcopy"
KEEP = {"TradDt": "date", "XpryDt": "expiry", "StrkPric": "strike", "OptnTp": "option_type",
        "OpnPric": "open", "HghPric": "high", "LwPric": "low", "ClsPric": "close", "LastPric": "ltp",
        "SttlmPric": "settle", "TtlTradgVol": "volume", "OpnIntrst": "oi", "UndrlygPric": "underlying",
        "NewBrdLotQty": "lot_size", "TckrSymb": "symbol"}


def trading_days(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def parse_bhavcopy(content: bytes, symbols: List[str]) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(content))
    df = pd.read_csv(z.open(z.namelist()[0]))
    df = df[(df["FinInstrmTp"] == "IDO") & (df["TckrSymb"].isin(symbols))]
    return df[list(KEEP)].rename(columns=KEEP)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NSE F&O UDiFF bhavcopy -> index option daily store")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--symbols", default="BANKNIFTY,NIFTY")
    ap.add_argument("--sleep", type=float, default=1.5, help="Seconds between requests")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args(argv)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"done": {}, "holiday": []}
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    sess = requests.Session()
    sess.headers.update(HEADERS)
    ok = skip = hol = fail = 0
    for d in trading_days(start, end):
        key = d.isoformat()
        if key in manifest["done"] or key in manifest["holiday"]:
            skip += 1
            continue
        url = URL.format(ymd=d.strftime("%Y%m%d"))
        for attempt in range(3):
            try:
                r = sess.get(url, timeout=30)
                break
            except requests.RequestException as exc:
                log.warning("%s attempt %d failed: %s", key, attempt + 1, exc)
                time.sleep(5 * (attempt + 1))
        else:
            fail += 1
            continue
        if r.status_code == 404:
            manifest["holiday"].append(key)
            hol += 1
        elif r.status_code != 200 or not r.content.startswith(b"PK"):
            log.warning("%s HTTP %s (%d bytes) — will retry on next run", key, r.status_code, len(r.content))
            fail += 1
            time.sleep(10)
            continue
        else:
            df = parse_bhavcopy(r.content, symbols)
            counts = {}
            for sym, g in df.groupby("symbol"):
                path = out / f"{sym.lower()}_options_daily_{d.year}.csv"
                g.to_csv(path, mode="a", header=not path.exists(), index=False)
                counts[sym] = len(g)
            manifest["done"][key] = counts
            ok += 1
            if ok % 20 == 0:
                log.info("%s done (%s); ok=%d holiday=%d fail=%d", key, counts, ok, hol, fail)
        manifest_path.write_text(json.dumps(manifest, indent=0))
        time.sleep(args.sleep)

    log.info("Finished: ok=%d skipped=%d holiday=%d fail=%d -> %s", ok, skip, hol, fail, out)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
