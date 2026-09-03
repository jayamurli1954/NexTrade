#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run ARASS v1.0 research backtest (NSE index + India VIX).

Examples:
  python -m research.run_arass_backtest --start 2016-01-01 --end 2026-08-01
  python -m research.run_arass_backtest --mode excel --excel "D:/Download/Historical Data_Nifty50-BankNifty_IndiaVix.xlsx"
  python -m research.run_arass_backtest --mode excel --options-store research/data/options/nifty_options_daily.csv --no-synthetic
  python -m research.run_arass_backtest --mode 5m
  python -m research.run_arass_backtest --spot-csv path/to/nifty.csv --vix-csv path/to/vix.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.arass.data_loader import load_arass_market_panel
from research.arass.definition import ARASS_PARAMS, ArassParams, build_arass_hypothesis, build_arass_strategy_draft
from research.arass.engine import ArassBacktestEngine
from research.arass.options_store import OptionsStore
from research.backtest_protocol import BacktestConstraints

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_arass")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ARASS v1.0 research backtest")
    ap.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2026-08-01")
    ap.add_argument("--mode", default="daily_expanded", choices=["daily_expanded", "5m", "excel"])
    ap.add_argument("--excel", default=None, help="Path to Nifty/BankNifty/VIX Excel workbook")
    ap.add_argument("--spot-csv", default=None)
    ap.add_argument("--vix-csv", default=None)
    ap.add_argument("--options-store", default=None, help="CSV/parquet of CE/PE daily OHLC")
    ap.add_argument(
        "--no-synthetic",
        action="store_true",
        help="Prefer real options OHLC from --options-store (BS fallback on misses)",
    )
    ap.add_argument("--capital", type=float, default=1_000_000.0)
    ap.add_argument("--out", default=None, help="JSON report path")
    args = ap.parse_args(argv)

    params = ArassParams(
        initial_capital=float(args.capital),
        use_synthetic_premiums=not bool(args.no_synthetic),
    )
    panel, provenance = load_arass_market_panel(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        mode=args.mode,
        spot_csv=args.spot_csv,
        vix_csv=args.vix_csv,
        excel_path=args.excel,
    )

    options_store = None
    if args.options_store:
        options_store = OptionsStore.load(args.options_store)
        provenance += f"|options_store:{args.options_store}|rows={len(options_store.df)}"

    hypothesis = build_arass_hypothesis()
    draft = build_arass_strategy_draft(params)
    engine = ArassBacktestEngine(params=params, options_store=options_store)
    result = engine.run(
        draft,
        {"panel": panel, "provenance": provenance, "options_store": options_store},
        constraints=BacktestConstraints(initial_capital=params.initial_capital),
    )

    metrics = result.extras.get("arass_metrics", {})
    filter_stats = result.extras.get("filter_stats", {})

    print("=" * 72)
    print(f"ARASS {params.version} | {args.symbol} | RESEARCH ONLY")
    print(f"Period: {result.period_start} -> {result.period_end}")
    print(f"Provenance: {provenance}")
    print(f"Hypothesis: {hypothesis.hypothesis_id}")
    print(f"Premium mode: {'synthetic_bs' if params.use_synthetic_premiums else 'options_ohlc'}")
    print(f"Options hits/misses: {result.extras.get('options_hits')}/{result.extras.get('options_misses')}")
    print("-" * 72)
    print(f"Trades:           {metrics.get('total_trades')}")
    print(f"Filter pass days: {filter_stats.get('filter_pass_days')} / {filter_stats.get('candidate_days')} "
          f"({filter_stats.get('pass_rate_pct', 0):.1f}%)")
    print(f"Win rate:         {metrics.get('win_rate_pct', 0):.1f}%")
    print(f"Profit factor:    {metrics.get('profit_factor')}")
    print(f"Expectancy:       INR {metrics.get('expectancy', 0):,.0f}")
    print(f"CAGR:             {metrics.get('cagr_pct', 0):.2f}%")
    print(f"Total return:     {metrics.get('total_return_pct', 0):.2f}%")
    print(f"Max drawdown:     {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"Sharpe:           {metrics.get('sharpe', 0):.2f}")
    print(f"Sortino:          {metrics.get('sortino', 0):.2f}")
    print(f"Calmar:           {metrics.get('calmar', 0):.2f}")
    print(f"Recovery factor:  {metrics.get('recovery_factor', 0):.2f}")
    print(f"Charges total:    INR {metrics.get('total_charges', 0):,.0f}")
    print(f"Yearly returns %: {metrics.get('yearly_returns')}")
    print("=" * 72)
    if params.use_synthetic_premiums:
        print("CAVEAT: Premiums are Black-Scholes(synthetic) from India VIX unless --no-synthetic + options store.")
    else:
        print("CAVEAT: Real options OHLC used when present; BS fallback on store misses. Daily OHLC only.")
    print("Not certified for paper/live. Do not maximize CAGR - review risk metrics first.")

    out = args.out
    if not out:
        out_dir = ROOT / "backtesting" / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = str(out_dir / f"arass_{args.symbol}_{result.period_start}_{result.period_end}.json")

    payload = {
        "run_id": result.run_id,
        "notes": result.notes,
        "metrics": metrics,
        "filter_stats": filter_stats,
        "provenance": provenance,
        "options_hits": result.extras.get("options_hits"),
        "options_misses": result.extras.get("options_misses"),
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }
    Path(out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
