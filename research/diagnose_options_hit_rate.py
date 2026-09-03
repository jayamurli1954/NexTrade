"""
MDW-1: Diagnose NIFTY options store coverage vs ARASS-style ATM straddle lookups.

Usage:
  python -m research.diagnose_options_hit_rate
  python -m research.diagnose_options_hit_rate --store research/data/options/nifty_options_daily.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.arass.indicators import atm_strike, nearest_thursday_expiry
from research.arass.options_store import OptionsStore
from research.market_warehouse import MarketWarehouse


def build_samples_from_store(store: OptionsStore, *, max_days: int = 400) -> list:
    """Use unique trading days in store; ATM ≈ median strike that day (proxy)."""
    df = store.df
    if df.empty:
        return []
    samples = []
    days = sorted(df["date"].drop_duplicates().tolist())[-max_days:]
    for day in days:
        day_df = df[df["date"] == day]
        # pick a representative strike present that day (mode / median)
        strikes = day_df["strike"].dropna()
        if strikes.empty:
            continue
        strike = float(strikes.median())
        strike = atm_strike(strike, 50.0)
        expiry = nearest_thursday_expiry(pd.Timestamp(day) + pd.Timedelta(hours=10))
        samples.append({"asof": pd.Timestamp(day), "expiry": expiry, "strike": strike})
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose options straddle hit rates (MDW-1)")
    parser.add_argument("--store", type=str, default="")
    parser.add_argument("--max-days", type=int, default=400)
    args = parser.parse_args()

    wh = MarketWarehouse()
    path = Path(args.store) if args.store else wh.options_path()
    store = OptionsStore.load(path)
    samples = build_samples_from_store(store, max_days=args.max_days)
    report = store.diagnose_straddle_coverage(symbol="NIFTY", samples=samples, strike_step=50.0)
    report["store_path"] = str(path)
    report["store_rows"] = int(len(store.df))
    wh.write_manifest("options_hit_rate_mdw1", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
