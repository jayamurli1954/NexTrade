#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build Mahesh-style CAR + DMA stock screener Excel (research / educational).

Uses local Kaggle 5m → daily resample. Not investment advice.
Not wired to paper/live execution.

Example:
  python -m research.build_car_dma_screener_excel
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.orb.data_loader import default_data_dir, load_ohlcv_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("CarDmaScreener")

INDEX_NAMES = {"NIFTY 50", "NIFTY BANK", "INDIA VIX"}


def _to_daily(df_5m: pd.DataFrame) -> pd.DataFrame:
    ohlc = df_5m.resample("1D").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return ohlc.dropna(subset=["open", "high", "low", "close"])


def _car_positive_streak(close: pd.Series) -> Tuple[Optional[pd.Timestamp], int, float]:
    """
    From the most recent 252-trading-day high, compute CAR =
    cumulative(sum of daily changes) / days_since_high.

    Returns (high_date, consecutive_positive_car_days_ending_today, latest_car).
    """
    if len(close) < 260:
        return None, 0, float("nan")

    roll_high = close.rolling(252, min_periods=252).max()
    # Most recent day that printed the rolling 1y high
    is_high = close >= (roll_high - 1e-9)
    high_idxs = np.where(is_high.fillna(False).to_numpy())[0]
    if len(high_idxs) == 0:
        return None, 0, float("nan")

    # Prefer the start of the latest high plateau: last index where high was made
    peak_i = int(high_idxs[-1])
    # Walk back to first day of this high episode within last 252 window
    peak_price = float(close.iloc[peak_i])
    start_i = peak_i
    while start_i > 0 and abs(float(close.iloc[start_i - 1]) - peak_price) < 1e-6:
        start_i -= 1
    # If peak is the last bar, CAR window empty
    if peak_i >= len(close) - 1:
        # still at high — treat CAR from peak inclusive with 0 change days
        return close.index[peak_i], 0, 0.0

    # Recenter: use earliest touch of the max price in the last 252 days
    window = close.iloc[-252:]
    max_px = float(window.max())
    first_touch_rel = int(np.argmax(window.to_numpy() >= max_px - 1e-9))
    peak_pos = len(close) - 252 + first_touch_rel
    peak_ts = close.index[peak_pos]

    changes = close.diff()
    # from day after peak through today
    seg = changes.iloc[peak_pos + 1 :]
    if seg.empty:
        return peak_ts, 0, 0.0

    cum = seg.cumsum()
    days = np.arange(1, len(seg) + 1, dtype=float)
    car = cum / days

    # consecutive days at end where CAR > 0
    streak = 0
    for v in car.iloc[::-1]:
        if float(v) > 0:
            streak += 1
        else:
            break
    return peak_ts, streak, float(car.iloc[-1])


def screen_symbol(daily: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
    if len(daily) < 260:
        return None
    close = daily["close"].astype(float)
    high = daily["high"].astype(float)
    open_ = daily["open"].astype(float)

    dma30 = close.rolling(30).mean()
    dma50 = close.rolling(50).mean()
    dma200 = close.rolling(200).mean()

    cmp_ = float(close.iloc[-1])
    d30 = float(dma30.iloc[-1])
    d50 = float(dma50.iloc[-1])
    d200 = float(dma200.iloc[-1])
    if not all(np.isfinite([cmp_, d30, d50, d200])) or d200 <= 0:
        return None

    dist_200 = (cmp_ - d200) / d200 * 100.0
    year_high = float(high.iloc[-252:].max())
    high_date, car_streak, car_val = _car_positive_streak(close)

    # ShareGenius (as-of last two sessions in data)
    prev_open = float(open_.iloc[-2])
    prev_close = float(close.iloc[-2])
    today_open = float(open_.iloc[-1])
    day_trend = prev_close - prev_open
    gap = today_open - prev_close
    if day_trend > 0 and gap > 0:
        sg = "BUY"
    elif day_trend < 0 and gap < 0:
        sg = "SHORT"
    else:
        sg = ""

    passes = (
        cmp_ > d30
        and cmp_ > d50
        and cmp_ > d200
        and dist_200 <= 10.0
        and car_streak >= 10
    )

    return {
        "Symbol": symbol,
        "AsOf": daily.index[-1].strftime("%Y-%m-%d"),
        "CMP": round(cmp_, 2),
        "DMA_30": round(d30, 2),
        "DMA_50": round(d50, 2),
        "DMA_200": round(d200, 2),
        "Dist_200DMA_Pct": round(dist_200, 2),
        "YearHigh_252": round(year_high, 2),
        "CAR_HighDate": high_date.strftime("%Y-%m-%d") if high_date is not None else "",
        "CAR_Value": round(car_val, 4) if np.isfinite(car_val) else None,
        "CAR_PosDays": int(car_streak),
        "Pass_CMP_gt_DMAs": bool(cmp_ > d30 and cmp_ > d50 and cmp_ > d200),
        "Pass_Dist_le_10": bool(dist_200 <= 10.0),
        "Pass_CAR_10d": bool(car_streak >= 10),
        "PASS_SCREENER": bool(passes),
        "SuggestedTarget_6_28pct": round(cmp_ * 1.0628, 2),
        "PrevOpen": round(prev_open, 2),
        "PrevClose": round(prev_close, 2),
        "TodayOpen": round(today_open, 2),
        "DayTrend": round(day_trend, 2),
        "Gap": round(gap, 2),
        "ShareGenius_Signal": sg,
    }


def build_workbook(rows: List[Dict[str, Any]], out_path: Path, *, universe_note: str) -> Path:
    all_df = pd.DataFrame(rows)
    if all_df.empty:
        raise RuntimeError("No symbol rows computed")

    passed = all_df[all_df["PASS_SCREENER"]].sort_values("Dist_200DMA_Pct", ascending=True)
    ranked = passed.copy()
    if not ranked.empty:
        ranked.insert(0, "Rank", range(1, len(ranked) + 1))

    dma_dist = all_df[(all_df["Pass_CMP_gt_DMAs"]) & (all_df["Pass_Dist_le_10"])].sort_values(
        ["CAR_PosDays", "Dist_200DMA_Pct"], ascending=[False, True]
    )
    near = all_df[all_df["Pass_CMP_gt_DMAs"]].sort_values(
        ["CAR_PosDays", "Dist_200DMA_Pct"], ascending=[False, True]
    )

    sg_buy = all_df[all_df["ShareGenius_Signal"] == "BUY"].sort_values("Gap", ascending=False)
    sg_short = all_df[all_df["ShareGenius_Signal"] == "SHORT"].sort_values("Gap", ascending=True)

    method = pd.DataFrame(
        [
            {"Item": "Source video", "Detail": "Mahesh Chander Kaushik — Stock screener in Google Colab (educational)"},
            {"Item": "Disclaimer", "Detail": "Educational only. Not SEBI advice / not investment advice."},
            {"Item": "Universe used", "Detail": universe_note},
            {"Item": "Video universe", "Detail": "NSE F&O underlying list (~210). This run uses local Kaggle 5m→daily symbols."},
            {"Item": "CAR", "Detail": "From first touch of 252d close high: CAR = cumsum(daily change)/days; need CAR>0 for 10 consecutive days"},
            {"Item": "DMA filters", "Detail": "CMP > 30 DMA and 50 DMA and 200 DMA"},
            {"Item": "Distance filter", "Detail": "(CMP-200DMA)/200DMA * 100 <= 10"},
            {"Item": "Rank", "Detail": "Among PASS rows, lowest Dist_200DMA_Pct first (buy-1/day rule from video)"},
            {"Item": "Target (video)", "Detail": "6.28% from CMP (informational column only)"},
            {"Item": "Sheets", "Detail": "CAR_DMA_PASSED=full pass; DMA_DIST_PASS=DMA+dist only; NEAR_DMA=above DMAs; ShareGenius_*=gap formula"},
            {"Item": "ShareGenius", "Detail": "PrevClose>PrevOpen and TodayOpen>PrevClose → BUY (and inverse SHORT)"},
            {"Item": "Generated_UTC", "Detail": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")},
            {"Item": "NexTrade note", "Detail": "Research export only. Phase 7P: not paper/live strategy authority."},
        ]
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xl:
        ranked.to_excel(xl, sheet_name="CAR_DMA_PASSED", index=False)
        dma_dist.to_excel(xl, sheet_name="DMA_DIST_PASS", index=False)
        near.to_excel(xl, sheet_name="NEAR_DMA", index=False)
        all_df.sort_values(["PASS_SCREENER", "Dist_200DMA_Pct"], ascending=[False, True]).to_excel(
            xl, sheet_name="ALL_SYMBOLS", index=False
        )
        sg_buy.to_excel(xl, sheet_name="ShareGenius_BUY", index=False)
        sg_short.to_excel(xl, sheet_name="ShareGenius_SHORT", index=False)
        method.to_excel(xl, sheet_name="METHODOLOGY", index=False)
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build CAR+DMA screener Excel")
    ap.add_argument("--data-dir", default=str(default_data_dir()))
    ap.add_argument(
        "--out",
        default=str(ROOT / "reports" / f"CAR_DMA_Screener_{datetime.now().strftime('%Y%m%d')}.xlsx"),
    )
    ap.add_argument("--max-symbols", type=int, default=None)
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    files = sorted(
        p for p in data_dir.glob("*_5minute.csv") if p.name[: -len("_5minute.csv")] not in INDEX_NAMES
    )
    if args.max_symbols:
        files = files[: int(args.max_symbols)]

    rows: List[Dict[str, Any]] = []
    for i, path in enumerate(files, 1):
        sym = path.name[: -len("_5minute.csv")]
        try:
            raw = load_ohlcv_csv(path)
            daily = _to_daily(raw)
            row = screen_symbol(daily, sym)
            if row:
                rows.append(row)
        except Exception as e:
            logger.warning("%s failed: %s", sym, e)
        if i % 20 == 0:
            logger.info("Processed %d / %d", i, len(files))

    out = build_workbook(
        rows,
        Path(args.out),
        universe_note=f"Local Kaggle 5m resampled daily — {len(rows)} symbols scored (not full 210 F&O list)",
    )
    passed_n = sum(1 for r in rows if r["PASS_SCREENER"])
    logger.info("Excel written: %s (passed=%d / scored=%d)", out, passed_n, len(rows))
    print(json.dumps({"out": str(out), "scored": len(rows), "passed": passed_n}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
