"""
ORB–VWAP long-only research backtest engine.

Research-only. Reads local Kaggle 5m CSVs. Does not touch paper/live risk or execution.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from research.arass.indicators import session_vwap
from research.orb.costs import estimate_equity_round_trip_cost
from research.orb.definition import ORB_PARAMS, OrbParams
from research.orb.metrics import OrbMetrics, compute_metrics

logger = logging.getLogger("OrbBacktestEngine")


def _hm_ts(day: pd.Timestamp, hm: Tuple[int, int]) -> pd.Timestamp:
    return pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=hm[0], minute=hm[1])


def _prepare_symbol(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["vwap"] = session_vwap(out)
    out["vol_sma"] = out["volume"].rolling(20, min_periods=20).mean()
    out["bar_range_pct"] = (out["high"] - out["low"]) / out["close"].replace(0, np.nan) * 100.0
    return out


def _prepare_nifty(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["vwap"] = session_vwap(out)
    return out


class OrbBacktestEngine:
    engine_name = "NEXTRADE_ORB_VWAP_RESEARCH_V1"

    def __init__(self, params: OrbParams = ORB_PARAMS):
        self.params = params

    def run(
        self,
        symbol_panels: Dict[str, pd.DataFrame],
        nifty_panel: pd.DataFrame,
        *,
        initial_capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        p = self.params
        capital0 = float(initial_capital if initial_capital is not None else p.initial_capital)
        capital = capital0

        prepared = {sym: _prepare_symbol(df) for sym, df in symbol_panels.items() if not df.empty}
        nifty = _prepare_nifty(nifty_panel)

        # trading calendar = union of symbol days intersecting nifty
        all_days = sorted(
            set().union(*[set(df.index.normalize().unique()) for df in prepared.values()])
            & set(nifty.index.normalize().unique())
        )

        trades: List[Dict[str, Any]] = []
        equity_curve: List[float] = [capital]
        signals_seen = 0
        days_with_signal = 0

        for day_ts in all_days:
            day = pd.Timestamp(day_ts).normalize()
            day_str = day.strftime("%Y-%m-%d")
            day_start_equity = capital
            day_trades = 0
            day_halted = False
            consecutive_losses = 0  # daily kill-switch (intraday ORB rule)
            traded_symbols = set()

            or_start = _hm_ts(day, p.or_start_hm)
            or_end = _hm_ts(day, p.or_end_hm)
            entry_start = _hm_ts(day, p.entry_start_hm)
            entry_end = _hm_ts(day, p.entry_end_hm)
            flat_at = _hm_ts(day, p.flat_hm)

            nifty_day = nifty[(nifty.index >= or_start) & (nifty.index <= flat_at)]
            if nifty_day.empty:
                equity_curve.append(capital)
                continue

            # Collect candidate signals chronologically across symbols
            candidates: List[Dict[str, Any]] = []
            for sym, df in prepared.items():
                day_df = df[(df.index >= or_start) & (df.index <= flat_at)]
                if len(day_df) < 10:
                    continue
                or_bars = day_df[(day_df.index >= or_start) & (day_df.index < or_end)]
                if len(or_bars) < 2:
                    continue
                or_high = float(or_bars["high"].max())
                or_low = float(or_bars["low"].min())
                ref = float(or_bars["open"].iloc[0]) or float(or_bars["close"].iloc[0])
                if ref <= 0:
                    continue
                or_width_pct = 100.0 * (or_high - or_low) / ref
                if or_width_pct > float(p.max_or_width_pct):
                    continue

                entry_bars = day_df[(day_df.index >= entry_start) & (day_df.index <= entry_end)]
                for ts, row in entry_bars.iterrows():
                    close = float(row["close"])
                    vol = float(row["volume"])
                    vol_sma = float(row["vol_sma"]) if pd.notna(row["vol_sma"]) else np.nan
                    vwap = float(row["vwap"]) if pd.notna(row["vwap"]) else np.nan
                    if not np.isfinite(vol_sma) or vol_sma <= 0 or not np.isfinite(vwap):
                        continue
                    if close <= or_high:
                        continue
                    if close <= vwap:
                        continue
                    if vol < float(p.volume_mult) * vol_sma:
                        continue
                    if float(row["bar_range_pct"]) > float(p.max_breakout_range_pct):
                        continue
                    if p.require_nifty_above_vwap:
                        if ts not in nifty_day.index:
                            # nearest prior nifty bar
                            prior = nifty_day[nifty_day.index <= ts]
                            if prior.empty:
                                continue
                            n_row = prior.iloc[-1]
                        else:
                            n_row = nifty_day.loc[ts]
                            if isinstance(n_row, pd.DataFrame):
                                n_row = n_row.iloc[-1]
                        n_close = float(n_row["close"])
                        n_vwap = float(n_row["vwap"]) if pd.notna(n_row["vwap"]) else np.nan
                        if not np.isfinite(n_vwap) or n_close <= n_vwap:
                            continue

                    stop = float(row["low"])
                    # Enforce minimum stop distance so sizing stays sane
                    min_stop_dist = close * 0.0025  # 0.25% of price
                    if (close - stop) < min_stop_dist:
                        stop = close - min_stop_dist
                    if stop >= close:
                        continue
                    risk_per_share = close - stop
                    if risk_per_share <= 0:
                        continue
                    target = close + float(p.reward_risk) * risk_per_share
                    candidates.append(
                        {
                            "symbol": sym,
                            "ts": ts,
                            "entry": close,
                            "stop": stop,
                            "target": target,
                            "or_high": or_high,
                            "or_low": or_low,
                            "or_width_pct": or_width_pct,
                            "volume_ratio": vol / vol_sma,
                            "day_df": day_df,
                        }
                    )
                    break  # first valid long signal per symbol per day

            if not candidates:
                equity_curve.append(capital)
                continue

            days_with_signal += 1
            candidates.sort(key=lambda c: (c["ts"], -c["volume_ratio"]))
            signals_seen += len(candidates)

            for cand in candidates:
                if day_halted or day_trades >= int(p.max_trades_per_day):
                    break
                if cand["symbol"] in traded_symbols:
                    continue
                if consecutive_losses >= int(p.max_consecutive_losses):
                    day_halted = True
                    break
                dd_pct = 100.0 * (day_start_equity - capital) / day_start_equity if day_start_equity else 0.0
                if dd_pct >= float(p.daily_loss_limit_pct):
                    day_halted = True
                    break

                risk_budget = capital * (float(p.risk_pct_capital) / 100.0)
                risk_ps = cand["entry"] - cand["stop"]
                if risk_ps <= 0 or capital < 1000:
                    continue
                qty = int(risk_budget // risk_ps)
                # Cash constraint (no leverage in research v1)
                max_qty = int(capital // float(cand["entry"])) if cand["entry"] > 0 else 0
                qty = min(qty, max_qty)
                if qty <= 0:
                    continue
                # Skip if costs would dominate planned risk
                planned_risk = risk_ps * qty
                if planned_risk < 50:
                    continue

                # Simulate path after entry bar
                path = cand["day_df"][cand["day_df"].index > cand["ts"]]
                path = path[path.index <= flat_at]
                exit_price = float(cand["entry"])
                exit_ts = cand["ts"]
                exit_reason = "EOD"
                for ets, erow in path.iterrows():
                    lo = float(erow["low"])
                    hi = float(erow["high"])
                    # conservative: stop before target if both in same bar
                    if lo <= cand["stop"]:
                        exit_price = float(cand["stop"])
                        exit_ts = ets
                        exit_reason = "STOP"
                        break
                    if hi >= cand["target"]:
                        exit_price = float(cand["target"])
                        exit_ts = ets
                        exit_reason = "TARGET"
                        break
                    exit_price = float(erow["close"])
                    exit_ts = ets
                    exit_reason = "EOD"

                costs = estimate_equity_round_trip_cost(
                    entry=float(cand["entry"]),
                    exit=exit_price,
                    qty=qty,
                    params=p,
                )
                gross = (exit_price - float(cand["entry"])) * qty
                net = gross - costs.total
                capital += net

                trade = {
                    "symbol": cand["symbol"],
                    "day": day_str,
                    "side": "BUY",
                    "entry_time": str(cand["ts"]),
                    "exit_time": str(exit_ts),
                    "entry": round(float(cand["entry"]), 4),
                    "stop": round(float(cand["stop"]), 4),
                    "target": round(float(cand["target"]), 4),
                    "exit": round(float(exit_price), 4),
                    "qty": qty,
                    "pnl_gross": round(float(gross), 2),
                    "costs": round(float(costs.total), 2),
                    "pnl_net": round(float(net), 2),
                    "exit_reason": exit_reason,
                    "or_width_pct": round(float(cand["or_width_pct"]), 3),
                    "volume_ratio": round(float(cand["volume_ratio"]), 3),
                    "r_multiple": round(float(net) / risk_budget, 3) if risk_budget else 0.0,
                }
                trades.append(trade)
                equity_curve.append(capital)
                traded_symbols.add(cand["symbol"])
                day_trades += 1
                if net <= 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

            if day_trades == 0:
                equity_curve.append(capital)

        metrics = compute_metrics(
            trades,
            equity_curve=equity_curve,
            initial_capital=capital0,
            trading_days=len(all_days),
        )
        return {
            "run_id": f"orb-{uuid.uuid4().hex[:10]}",
            "engine_name": self.engine_name,
            "strategy_id": p.strategy_id,
            "strategy_version": p.version,
            "period_start": str(all_days[0].date()) if all_days else None,
            "period_end": str(all_days[-1].date()) if all_days else None,
            "initial_capital": capital0,
            "final_capital": round(capital, 2),
            "metrics": metrics.to_dict(),
            "signals_seen": signals_seen,
            "days_with_signal": days_with_signal,
            "trading_days": len(all_days),
            "symbols": sorted(prepared.keys()),
            "trades": trades,
            "equity_curve_tail": [round(float(x), 2) for x in equity_curve[-50:]],
            "note": "Research-only ORB–VWAP long-only. Not paper/live eligible under Phase 7P freeze.",
        }
