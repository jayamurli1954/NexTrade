#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run CAL-2 NIFTY calendar / rollover spread research backtest.

Examples:
  python -m research.run_calendar_spread_backtest --start 2020-01-01 --end 2026-07-28
  python -m research.run_calendar_spread_backtest --excel "D:/Download/Historical Data_Nifty50-BankNifty_IndiaVix.xlsx"
  python -m research.run_calendar_spread_backtest --spot-csv research/data/indices/nifty_daily.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.arass.excel_index_loader import DEFAULT_INDEX_EXCEL, load_index_workbook
from research.arass.options_store import OptionsStore, default_store_dir
from research.calendar_spread.definition import CAL_PARAMS, CalendarSpreadParams, params_to_dict
from research.calendar_spread.engine import CalendarSpreadEngine
from research.calendar_spread.signals import band_for_mode, parse_diff_mode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_calendar_spread")


def _load_spot(*, excel: str | None, spot_csv: str | None, start: str, end: str):
    if spot_csv:
        path = Path(spot_csv)
        df = __import__("pandas").read_csv(path, parse_dates=True, index_col=0)
        df.columns = [str(c).lower() for c in df.columns]
        df = df[(df.index >= start) & (df.index <= end)]
        return df, f"spot_csv:{path}"
    path = Path(excel) if excel else DEFAULT_INDEX_EXCEL
    frames = load_index_workbook(path, start=start, end=end)
    return frames["NIFTY"], f"excel:{path}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CAL-2 calendar spread research backtest")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-07-28")
    ap.add_argument("--excel", default=None)
    ap.add_argument("--spot-csv", default=None)
    ap.add_argument(
        "--options-store",
        default=str(default_store_dir() / "nifty_options_daily.csv"),
    )
    ap.add_argument("--capital", type=float, default=1_000_000.0)
    ap.add_argument(
        "--diff-mode",
        default="far_minus_near",
        choices=["far_minus_near", "next_minus_near"],
        help="Entry differential: far−near (monthly debit) or next−near (weekly roll)",
    )
    ap.add_argument(
        "--pts-band",
        default=None,
        help="Override band as LO:HI (default depends on --diff-mode)",
    )
    ap.add_argument("--out", default=None, help="JSON report path")
    args = ap.parse_args(argv)

    spot, provenance = _load_spot(
        excel=args.excel, spot_csv=args.spot_csv, start=args.start, end=args.end
    )
    store_path = Path(args.options_store)
    if not store_path.exists():
        logger.error("Options store not found: %s", store_path)
        return 2
    options = OptionsStore.load(store_path)
    provenance += f"|options:{store_path}|rows={len(options.df)}"

    mode = parse_diff_mode(args.diff_mode)
    lo, hi, exit_below = band_for_mode(mode)
    if args.pts_band:
        parts = str(args.pts_band).replace(",", ":").split(":")
        if len(parts) != 2:
            logger.error("--pts-band must be LO:HI")
            return 2
        lo, hi = float(parts[0]), float(parts[1])
    params = CalendarSpreadParams(
        initial_capital=float(args.capital),
        diff_mode=mode,
        pts_band_lo=float(lo),
        pts_band_hi=float(hi),
        exit_diff_below=float(exit_below),
    )
    engine = CalendarSpreadEngine(params=params)
    report = engine.run(spot, options, initial_capital=params.initial_capital)

    m = report["metrics"]
    fs = report["filter_stats"]
    out = {
        "params": params_to_dict(params),
        "provenance": provenance,
        "report": {
            k: report[k]
            for k in (
                "run_id",
                "engine_name",
                "params_version",
                "period_start",
                "period_end",
                "metrics",
                "filter_stats",
                "notes",
                "trades",
            )
        },
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "research" / "data" / "validation" / "calendar_spread_backtest_latest.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote %s", out_path)

    print("=" * 72)
    print(f"CAL-2 {params.version} | NIFTY | RESEARCH ONLY (not paper/live)")
    print(f"Period: {report['period_start']} -> {report['period_end']}")
    print(f"Diff mode: {params.diff_mode} | exit_below={params.exit_diff_below}")
    print(f"Provenance: {provenance}")
    print("-" * 72)
    print(f"Trades:              {m.get('total_trades')}")
    print(f"Pts-band hit rate:   {m.get('pts_band_hit_rate_pct')}% "
          f"({m.get('pts_band_hits')}/{m.get('pts_band_candidates')}) "
          f"band=[{params.pts_band_lo},{params.pts_band_hi}]")
    print(f"Candidate diffs:     min/med/max = "
          f"{fs.get('candidate_diff_min')}/{fs.get('candidate_diff_median')}/{fs.get('candidate_diff_max')}")
    print(f"Win rate:            {m.get('win_rate_pct')}%")
    print(f"Profit factor:       {m.get('profit_factor')}")
    print(f"Net PnL:             INR {m.get('net_pnl'):,.2f}")
    print(f"Charges:             INR {m.get('total_charges'):,.2f}")
    print(f"Total return:        {m.get('total_return_pct')}%")
    print(f"Max drawdown:        {m.get('max_drawdown_pct')}%")
    print(f"Avg monthly return:  {m.get('avg_monthly_return_pct')}%")
    print(f"Months in 2-4%:      {m.get('months_in_target_2_to_4')}/{m.get('months_total')}")
    print(f"Exit reasons:        {m.get('exit_reasons')}")
    print(f"Skips gap/zone/exp/prem: "
          f"{fs.get('skip_gap')}/{fs.get('skip_zone')}/{fs.get('skip_expiry')}/{fs.get('skip_premium')}")
    print("=" * 72)
    print(report["notes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
