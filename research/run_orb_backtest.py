#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run ORB–VWAP equity research backtest on local Kaggle 5m data.

Examples:
  python -m research.run_orb_backtest --start 2023-01-01 --end 2024-12-31
  python -m research.run_orb_backtest --start 2022-01-01 --end 2025-12-31 --max-symbols 30
  python -m research.run_orb_backtest --symbols RELIANCE,TCS,INFY,HDFCBANK,SBIN --start 2020-01-01 --end 2024-12-31
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

from research.orb.data_loader import (
    default_data_dir,
    load_nifty_panel,
    load_symbol_panels,
    resolve_symbols,
)
from research.orb.definition import OrbParams
from research.orb.engine import OrbBacktestEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_orb")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ORB–VWAP research backtest (Kaggle 5m)")
    ap.add_argument("--data-dir", default=str(default_data_dir()))
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--symbols", default=None, help="Comma-separated symbols (default: watchlist ∩ Kaggle)")
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--capital", type=float, default=200_000.0)
    ap.add_argument("--risk-pct", type=float, default=0.5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error("Data dir missing: %s", data_dir)
        return 2

    sym_list = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    symbols = resolve_symbols(
        data_dir,
        symbols=sym_list,
        use_watchlist=sym_list is None,
        max_symbols=args.max_symbols,
    )
    if not symbols:
        logger.error("No symbols resolved")
        return 2

    logger.info("Loading Nifty + %d symbols from %s (%s → %s)", len(symbols), data_dir, args.start, args.end)
    nifty = load_nifty_panel(data_dir, start=args.start, end=args.end)
    panels = load_symbol_panels(data_dir, symbols, start=args.start, end=args.end)
    logger.info("Loaded panels=%d nifty_bars=%d", len(panels), len(nifty))

    params = OrbParams(initial_capital=float(args.capital), risk_pct_capital=float(args.risk_pct))
    engine = OrbBacktestEngine(params=params)
    report = engine.run(panels, nifty, initial_capital=float(args.capital))

    out = Path(args.out) if args.out else ROOT / "backtesting" / "results" / (
        f"orb_{args.start}_{args.end}_{len(panels)}sym.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    m = report["metrics"]
    logger.info(
        "ORB done trades=%s win=%.1f%% pf=%.2f ret=%.2f%% maxDD=%.2f%% sharpe=%.2f → %s",
        m.get("total_trades"),
        m.get("win_rate_pct", 0),
        m.get("profit_factor", 0),
        m.get("total_return_pct", 0),
        m.get("max_drawdown_pct", 0),
        m.get("sharpe", 0),
        out,
    )
    print(json.dumps({"out": str(out), "metrics": m, "symbols": len(panels)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
