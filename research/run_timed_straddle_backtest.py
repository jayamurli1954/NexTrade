#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Timed intraday short straddle/strangle research backtest (5m index + VIX, synthetic premiums).

Examples:
  python -m research.run_timed_straddle_backtest --symbol NIFTY --start 2016-01-01
  python -m research.run_timed_straddle_backtest --symbol NIFTY --sl-pct 30 --entry 09:20 --exit 15:15
  python -m research.run_timed_straddle_backtest --symbol BANKNIFTY --end 2024-11-20 --points 0
  python -m research.run_timed_straddle_backtest --sweep          # small robustness grid
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import pickle
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from research.timed_straddle.data import OPTIONS_CSV, build_expiry_calendar, build_panel, load_5m, load_real_options
from research.timed_straddle.engine import TimedStraddleEngine
from research.timed_straddle.metrics import breakdown, summarize
from research.timed_straddle.params import TimedStraddleParams
from research.timed_straddle.pricing import IVCalibration, calibrate_from_real_options

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_timed_straddle")

OUT_DIR = ROOT / "research" / "data" / "timed_straddle"


def _hm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def get_calibration(rebuild: bool = False) -> IVCalibration:
    from research.timed_straddle import pricing

    stem = f"iv_calibration_nifty_tb{pricing.TIME_BLEND:.2f}"
    CAL_CACHE = OUT_DIR / f"{stem}.pkl"
    if CAL_CACHE.exists() and not rebuild:
        return pickle.loads(CAL_CACHE.read_bytes())
    logger.info("Calibrating IV/VIX ratios on real NSE option prices (one-off)...")
    cal = calibrate_from_real_options(load_real_options(), load_5m("NIFTY"), load_5m("INDIAVIX"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CAL_CACHE.write_bytes(pickle.dumps(cal))
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(cal.to_dict(), indent=1))
    logger.info("Calibration stats: %s", cal.stats)
    return cal


def run_once(params: TimedStraddleParams, panel, expiry_map, cal, margin: float):
    trades = TimedStraddleEngine(params, cal).run(panel, expiry_map)
    return trades, summarize(trades, margin)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Timed short straddle/strangle research backtest")
    ap.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--entry", default="09:20")
    ap.add_argument("--exit", default="15:15")
    ap.add_argument("--points", type=float, default=0.0, help="Points from ATM (0 = straddle)")
    ap.add_argument("--wings", type=float, default=None, help="Buy wings this many points beyond shorts")
    ap.add_argument("--sl-pct", type=float, default=25.0)
    ap.add_argument("--no-trail", action="store_true")
    ap.add_argument("--target", type=float, default=None)
    ap.add_argument("--max-loss", type=float, default=None)
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--slippage", type=float, default=None)
    ap.add_argument("--margin", type=float, default=None, help="Capital per trade for % stats")
    ap.add_argument("--no-calibration", action="store_true", help="Raw VIX as IV")
    ap.add_argument("--rebuild-calibration", action="store_true")
    ap.add_argument("--time-blend", type=float, default=None,
                    help="Trading-time weight for theta (default pricing.TIME_BLEND=0.75)")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args(argv)

    params = TimedStraddleParams(
        symbol=args.symbol, entry_hm=_hm(args.entry), exit_hm=_hm(args.exit),
        points_from_atm=args.points, buy_wings=args.wings is not None,
        wing_points=args.wings or 500.0, sl_pct=args.sl_pct, trail_sl_to_cost=not args.no_trail,
        target_rupees=args.target, max_loss_rupees=args.max_loss, lots=args.lots,
        slippage_points=args.slippage,
    )
    # Rough SPAN+exposure for 1 lot naked straddle (~₹2.3L Nifty / ₹1.6L BankNifty in 2026);
    # hedged (wings) needs far less. Override with --margin.
    margin = args.margin or (params.lots * (90_000.0 if params.buy_wings else 230_000.0)
                             if args.symbol == "NIFTY" else params.lots * (60_000.0 if params.buy_wings else 160_000.0))

    if args.time_blend is not None:
        from research.timed_straddle import pricing

        pricing.TIME_BLEND = float(args.time_blend)
    cal = IVCalibration.identity() if args.no_calibration else get_calibration(args.rebuild_calibration)
    panel = build_panel(args.symbol, args.start, args.end)
    real_exp = load_real_options(OPTIONS_CSV)["expiry"].unique() if args.symbol == "NIFTY" and OPTIONS_CSV.exists() else None
    expiry_map = build_expiry_calendar(args.symbol, panel.index.normalize().unique(), real_exp)
    logger.info("Panel %s bars, %s days with an expiry", len(panel), len(expiry_map))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.tag or f"{args.symbol.lower()}_{args.entry.replace(':', '')}_sl{int(args.sl_pct)}_p{int(args.points)}"

    if args.sweep:
        rows = []
        for entry, sl, pts, trail in itertools.product(["09:20", "09:45", "10:30", "12:00"], [20, 30, 40, 60],
                                                       [0.0, 1.0 * params.strike_step * 2], [True, False]):
            pr = replace(params, entry_hm=_hm(entry), sl_pct=float(sl), points_from_atm=pts, trail_sl_to_cost=trail)
            _, s = run_once(pr, panel, expiry_map, cal, margin)
            rows.append({"entry": entry, "sl_pct": sl, "points": pts, "trail": trail,
                         **{k: s.get(k) for k in ("trades", "net_pnl", "win_rate_pct", "profit_factor",
                                                   "max_drawdown", "sharpe_daily_ann", "cagr_on_margin_pct")}})
            logger.info("%s", rows[-1])
        df = pd.DataFrame(rows).sort_values("sharpe_daily_ann", ascending=False)
        df.to_csv(OUT_DIR / f"sweep_{args.symbol.lower()}.csv", index=False)
        print(df.to_string(index=False))
        return 0

    trades, summary = run_once(params, panel, expiry_map, cal, margin)
    if trades.empty:
        logger.error("No trades.")
        return 1
    trades["year"] = trades["date"].dt.year
    trades["weekday"] = trades["date"].dt.day_name().str[:3]
    trades["vix_bucket"] = pd.cut(trades["vix_entry"], [0, 12, 15, 18, 22, 30, 100])
    report = {
        "params": params.to_dict(),
        "calibration": cal.stats or "identity (raw VIX)",
        "summary": summary,
        "by_year": breakdown(trades, "year").reset_index().to_dict("records"),
        "by_dte": breakdown(trades, "dte").reset_index().to_dict("records"),
        "by_vix": breakdown(trades, "vix_bucket").reset_index().astype({"vix_bucket": str}).to_dict("records"),
    }
    trades.drop(columns=["legs"]).to_csv(OUT_DIR / f"trades_{tag}.csv", index=False)
    (OUT_DIR / f"report_{tag}.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    for k in ("by_year", "by_dte", "by_vix"):
        print(f"\n{k}:")
        print(pd.DataFrame(report[k]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
