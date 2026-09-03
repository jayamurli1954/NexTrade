"""Diagnose ARASS filter rejection reasons on a loaded panel (research)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.arass.data_loader import load_arass_market_panel
from research.arass.definition import ARASS_PARAMS
from research.arass.filters import evaluate_filters
from research.arass.indicators import adx, ema, session_vwap


def main():
    panel, prov = load_arass_market_panel(start="2016-01-01", end="2026-08-01")
    df = panel.copy()
    df.columns = [c.lower() for c in df.columns]
    daily = (
        df.groupby(df.index.normalize())
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna()
    )
    daily["ema20"] = ema(daily["close"], 20)
    daily["ema50"] = ema(daily["close"], 50)
    daily["adx"] = adx(daily["high"], daily["low"], daily["close"], 14)
    day_index = df.index.normalize()
    df["ema20"] = day_index.map(daily["ema20"])
    df["ema50"] = day_index.map(daily["ema50"])
    df["adx"] = day_index.map(daily["adx"])
    df["vwap"] = session_vwap(df)

    gap_map = {}
    or_map = {}
    prev_close = None
    p = ARASS_PARAMS
    for day, g in df.groupby(df.index.normalize()):
        day = pd.Timestamp(day)
        open_px = float(g.iloc[0]["open"])
        gap_map[day] = ((open_px - prev_close) / prev_close * 100.0) if prev_close else 0.0
        or_end = day + pd.Timedelta(hours=10, minutes=0)
        or_slice = g[(g.index >= day + pd.Timedelta(hours=9, minutes=15)) & (g.index <= or_end)]
        or_map[day] = (float(or_slice["high"].max()) - float(or_slice["low"].min())) / open_px * 100.0
        prev_close = float(g.iloc[-1]["close"])

    reasons = Counter()
    allowed = 0
    checked = 0
    for day, g in df.groupby(df.index.normalize()):
        # sample 10:35 bar
        target = pd.Timestamp(day) + pd.Timedelta(hours=10, minutes=35)
        if target not in g.index:
            idx = g.index[g.index.get_indexer([target], method="nearest")[0]]
        else:
            idx = target
        row = g.loc[idx]
        fr = evaluate_filters(
            ts=idx,
            spot=float(row["close"]),
            vwap=float(row["vwap"]) if np.isfinite(row["vwap"]) else float(row["close"]),
            ema20=float(row["ema20"]) if np.isfinite(row["ema20"]) else float(row["close"]),
            ema50=float(row["ema50"]) if np.isfinite(row["ema50"]) else float(row["close"]),
            adx_val=float(row["adx"]) if np.isfinite(row["adx"]) else 100.0,
            vix=float(row["vix"]),
            gap_pct=gap_map[pd.Timestamp(day)],
            opening_range_pct=or_map[pd.Timestamp(day)],
            params=p,
            event_dates=set(),
        )
        checked += 1
        if fr.allowed:
            allowed += 1
        for r in fr.reasons:
            reasons[r] += 1
    print("provenance", prov)
    print("checked", checked, "allowed", allowed)
    print("top reasons", reasons.most_common(15))


if __name__ == "__main__":
    main()
