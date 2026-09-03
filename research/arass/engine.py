"""
ARASS short-straddle research simulator.

Research-only. Uses synthetic BS premiums from India VIX unless options OHLC provided.
Does not touch paper/live risk or execution (OIE-001 safe).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

from contracts.strategy_research import BacktestMetricsSummary, StrategyDefinitionDraft
from research.arass.costs import estimate_straddle_round_trip_cost
from research.arass.definition import ARASS_PARAMS, ArassParams, build_arass_strategy_draft
from research.arass.filters import DEFAULT_EVENT_DATES, evaluate_filters
from research.arass.indicators import (
    adx,
    atr,
    atm_strike,
    black_scholes_price,
    ema,
    nearest_thursday_expiry,
    nifty_lot_size,
    session_vwap,
    years_to_expiry,
)
from research.arass.metrics import ArassMetrics, compute_metrics
from research.backtest_protocol import BacktestConstraints, BacktestCostModel, BacktestResult

logger = logging.getLogger("ArassBacktestEngine")


class ArassBacktestEngine:
    engine_name = "NEXTRADE_ARASS_RESEARCH_V1"

    def __init__(
        self,
        params: ArassParams = ARASS_PARAMS,
        event_dates: Optional[Set[str]] = None,
        options_store: Any = None,
    ):
        self.params = params
        self.event_dates = event_dates if event_dates is not None else set(DEFAULT_EVENT_DATES)
        self.options_store = options_store
        self._options_hits = 0
        self._options_misses = 0

    def run(
        self,
        strategy: StrategyDefinitionDraft,
        market_data: Any,
        *,
        costs: Optional[BacktestCostModel] = None,
        constraints: Optional[BacktestConstraints] = None,
    ) -> BacktestResult:
        """
        market_data: DataFrame with open/high/low/close/volume/vix
          OR dict {"panel": DataFrame, "provenance": str, "options_store": OptionsStore}
        """
        _ = costs  # ARASS uses its own NSE FO cost model from params
        constraints = constraints or BacktestConstraints(initial_capital=self.params.initial_capital)
        if isinstance(market_data, dict):
            panel = market_data["panel"]
            provenance = str(market_data.get("provenance", ""))
            if market_data.get("options_store") is not None:
                self.options_store = market_data["options_store"]
        else:
            panel = market_data
            provenance = "caller_panel"

        report = self.run_panel(panel, initial_capital=constraints.initial_capital)
        m = report["metrics"]
        summary = BacktestMetricsSummary(
            total_trades=m.total_trades,
            win_rate_pct=m.win_rate_pct,
            profit_factor=0.0 if not np.isfinite(m.profit_factor) else float(m.profit_factor),
            sharpe=m.sharpe,
            sortino=m.sortino,
            max_drawdown_pct=m.max_drawdown_pct,
            total_return_pct=m.total_return_pct,
            turnover=float(m.total_charges),
        )
        premium_mode = (
            "synthetic_bs_vix"
            if self.params.use_synthetic_premiums
            else f"options_ohlc(hits={self._options_hits},misses={self._options_misses})"
        )
        return BacktestResult(
            run_id=report["run_id"],
            engine_name=self.engine_name,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            period_start=report["period_start"],
            period_end=report["period_end"],
            metrics=summary,
            cost_model=BacktestCostModel(
                transaction_cost_bps=self.params.exchange_txn_bps,
                slippage_bps=self.params.slippage_premium_pct * 100.0,
            ),
            constraints=constraints,
            trades=report["trades"],
            equity_curve=report["equity_curve"],
            notes=(
                f"ARASS research run. provenance={provenance}. "
                f"premium_mode={premium_mode}. "
                "Not certified for paper/live."
            ),
            extras={
                "arass_metrics": m.to_dict(),
                "filter_stats": report["filter_stats"],
                "provenance": provenance,
                "paused_months": report["paused_months"],
                "options_hits": self._options_hits,
                "options_misses": self._options_misses,
            },
        )

    def run_panel(self, panel: pd.DataFrame, initial_capital: Optional[float] = None) -> Dict[str, Any]:
        p = self.params
        capital0 = float(initial_capital if initial_capital is not None else p.initial_capital)
        df = panel.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        required = {"open", "high", "low", "close", "vix"}
        missing = required - set(c.lower() for c in df.columns)
        # normalize cols
        df.columns = [c.lower() for c in df.columns]
        if missing:
            raise ValueError(f"Panel missing columns: {sorted(missing)}")

        # Daily-based trend indicators (correct lookback even when bars are expanded 5m)
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
        # Rough ATM straddle proxy ~ spot * IV * sqrt(T); use T≈5/365 for premium ATR scale
        df["premium_proxy"] = df["close"] * (df["vix"] / 100.0) * float(np.sqrt(5.0 / 365.0))
        df["prem_atr"] = atr(df["premium_proxy"], df["premium_proxy"] * 0.98, df["premium_proxy"], 14)

        # Daily gap + opening range from session bars
        day_groups = df.groupby(df.index.normalize())
        gap_map: Dict[pd.Timestamp, float] = {}
        or_map: Dict[pd.Timestamp, float] = {}
        prev_close = None
        for day, g in day_groups:
            day = pd.Timestamp(day)
            open_px = float(g.iloc[0]["open"])
            if prev_close and prev_close > 0:
                gap_map[day] = (open_px - prev_close) / prev_close * 100.0
            else:
                gap_map[day] = 0.0
            or_end = day + pd.Timedelta(hours=p.opening_range_end_hm[0], minutes=p.opening_range_end_hm[1])
            or_slice = g[(g.index >= day + pd.Timedelta(hours=9, minutes=15)) & (g.index <= or_end)]
            if len(or_slice) == 0:
                or_slice = g.iloc[: max(1, len(g) // 6)]
            or_high = float(or_slice["high"].max())
            or_low = float(or_slice["low"].min())
            or_map[day] = (or_high - or_low) / open_px * 100.0 if open_px else 999.0
            prev_close = float(g.iloc[-1]["close"])

        capital = capital0
        equity_curve: List[float] = [capital]
        equity_days: List[str] = []
        trades: List[Dict[str, Any]] = []
        traded_bars = 0
        filter_pass_days = 0
        candidate_days = 0
        paused_months: List[str] = []

        day_loss_count = 0
        day_pnl = 0.0
        week_pnl = 0.0
        month_start_equity = capital
        current_day = None
        current_week = None
        current_month = None
        paused_until_month = None
        open_trade: Optional[Dict[str, Any]] = None

        entry_start = p.entry_start_hm
        entry_end = p.entry_end_hm
        time_exit = p.time_exit_hm

        for ts, row in df.iterrows():
            day = pd.Timestamp(ts).normalize()
            week = (day - pd.Timedelta(days=day.weekday())).date().isoformat()
            month = f"{day.year:04d}-{day.month:02d}"

            if current_day != day:
                # day roll
                if current_day is not None:
                    equity_curve.append(capital)
                    equity_days.append(str(current_day.date()))
                current_day = day
                day_loss_count = 0
                day_pnl = 0.0
                candidate_days += 1

            if current_week != week:
                current_week = week
                week_pnl = 0.0
            if current_month != month:
                current_month = month
                month_start_equity = capital
                if paused_until_month and month > paused_until_month:
                    paused_until_month = None

            # Manage open position
            if open_trade is not None:
                traded_bars += 1
                spot_close = float(row["close"])
                spot_high = float(row["high"])
                spot_low = float(row["low"])
                iv = float(row["vix"]) / 100.0

                # Running extremes from entry (MAE) — avoids double-counting H then L path artifacts
                open_trade["max_high"] = max(float(open_trade.get("max_high", spot_close)), spot_high)
                open_trade["min_low"] = min(float(open_trade.get("min_low", spot_close)), spot_low)

                ce_c, pe_c = self._mark_premiums(spot_close, open_trade, ts, iv, field="close")
                # For short straddles, daily HIGH is the adverse premium mark when OHLC store is used
                ce_u, pe_u = self._mark_premiums(
                    open_trade["max_high"], open_trade, ts, iv, field="high"
                )
                ce_d, pe_d = self._mark_premiums(
                    open_trade["min_low"], open_trade, ts, iv, field="high"
                )
                # For a short straddle, adverse = highest combined premium among close/up/down marks
                candidates = [
                    (ce_c + pe_c, ce_c, pe_c, "close"),
                    (ce_u + pe_u, ce_u, pe_u, "high"),
                    (ce_d + pe_d, ce_d, pe_d, "low"),
                ]
                worst = max(candidates, key=lambda x: x[0])
                straddle_close = ce_c + pe_c
                straddle_adverse = worst[0]
                entry_straddle = open_trade["entry_straddle"]
                pnl_gross_per = entry_straddle - straddle_close
                profit_pct = (pnl_gross_per / entry_straddle * 100.0) if entry_straddle else 0.0

                open_trade["mtm_ce"] = ce_c
                open_trade["mtm_pe"] = pe_c
                open_trade["mtm_straddle"] = straddle_close

                # Stop loss on adverse premium
                sl_dist = open_trade["sl_premium"]
                if straddle_adverse >= entry_straddle + sl_dist:
                    self._close_trade(
                        open_trade, ts, worst[1], worst[2], capital_ref=capital, reason="SL"
                    )
                    capital, day_pnl, week_pnl, day_loss_count = self._apply_close(
                        open_trade, capital, day_pnl, week_pnl, day_loss_count, trades
                    )
                    open_trade = None
                    continue

                if profit_pct >= p.profit_take_1_pct and not open_trade.get("pt1_hit"):
                    open_trade["pt1_hit"] = True
                    open_trade["trail_floor"] = entry_straddle * (1.0 - p.profit_take_1_pct / 200.0)
                if profit_pct >= p.profit_take_2_pct:
                    self._close_trade(
                        open_trade, ts, ce_c, pe_c, capital_ref=capital, reason="PT75"
                    )
                    capital, day_pnl, week_pnl, day_loss_count = self._apply_close(
                        open_trade, capital, day_pnl, week_pnl, day_loss_count, trades
                    )
                    open_trade = None
                    continue

                if open_trade.get("pt1_hit") and p.trail_after_pt1:
                    floor = float(open_trade.get("trail_floor", entry_straddle))
                    # Tighten trail as premium decays (short)
                    open_trade["trail_floor"] = min(floor, straddle_close * 1.05)
                    if straddle_close >= open_trade["trail_floor"] and profit_pct < p.profit_take_1_pct * 0.5:
                        self._close_trade(open_trade, ts, ce_c, pe_c, capital_ref=capital, reason="TRAIL")
                        capital, day_pnl, week_pnl, day_loss_count = self._apply_close(
                            open_trade, capital, day_pnl, week_pnl, day_loss_count, trades
                        )
                        open_trade = None
                        continue

                if (ts.hour, ts.minute) >= time_exit:
                    self._close_trade(open_trade, ts, ce_c, pe_c, capital_ref=capital, reason="TIME_EXIT")
                    capital, day_pnl, week_pnl, day_loss_count = self._apply_close(
                        open_trade, capital, day_pnl, week_pnl, day_loss_count, trades
                    )
                    open_trade = None
                    continue

                continue

            # Circuit breakers
            if paused_until_month is not None:
                continue
            month_dd = (capital - month_start_equity) / month_start_equity * 100.0 if month_start_equity else 0.0
            if month_dd <= -p.monthly_drawdown_pause_pct:
                paused_until_month = month
                paused_months.append(month)
                continue
            if week_pnl <= -p.weekly_loss_limit_pct / 100.0 * capital0:
                continue
            if day_pnl <= -p.daily_loss_limit_pct / 100.0 * capital0:
                continue
            if day_loss_count >= p.max_losses_per_day:
                continue

            # Entry window only
            hm = (ts.hour, ts.minute)
            if not (entry_start <= hm <= entry_end):
                continue

            # One attempt per day
            if any(t.get("entry_day") == str(day.date()) for t in trades):
                continue

            gap_pct = gap_map.get(day, 0.0)
            or_pct = or_map.get(day, 999.0)
            fr = evaluate_filters(
                ts=ts,
                spot=float(row["close"]),
                vwap=float(row["vwap"]) if np.isfinite(row["vwap"]) else float(row["close"]),
                ema20=float(row["ema20"]) if np.isfinite(row["ema20"]) else float(row["close"]),
                ema50=float(row["ema50"]) if np.isfinite(row["ema50"]) else float(row["close"]),
                adx_val=float(row["adx"]) if np.isfinite(row["adx"]) else 100.0,
                vix=float(row["vix"]),
                gap_pct=gap_pct,
                opening_range_pct=or_pct,
                params=p,
                event_dates=self.event_dates,
            )
            if not fr.allowed:
                continue
            filter_pass_days += 1

            spot = float(row["close"])
            strike = atm_strike(spot, p.strike_step)
            expiry = nearest_thursday_expiry(ts)
            iv = float(row["vix"]) / 100.0
            # Prefer real options OHLC when store available (MDW-1); else synthetic BS
            ce, pe = self._mark_premiums(spot, {
                "expiry": expiry,
                "strike": strike,
                "symbol": p.universe_primary,
            }, ts, iv, field="close")
            entry_straddle = ce + pe
            if entry_straddle <= 0:
                continue

            prem_atr = float(row["prem_atr"]) if np.isfinite(row["prem_atr"]) else entry_straddle * 0.15
            sl_premium = max(p.premium_atr_sl_mult * prem_atr, entry_straddle * 0.25)

            lot = nifty_lot_size(ts, p.default_lot_size)
            max_risk = capital * (p.max_risk_pct_capital / 100.0)
            # risk ≈ sl_premium * qty
            raw_qty = max_risk / max(sl_premium, 1e-6)
            lots = max(int(raw_qty // lot), 0)
            if lots < 1:
                continue
            qty = lots * lot

            # margin util proxy ≈ straddle notional * 0.2 (SPAN-like research proxy)
            margin_proxy = entry_straddle * qty * 0.20
            open_trade = {
                "trade_id": uuid.uuid4().hex[:12],
                "entry_time": str(ts),
                "entry_day": str(day.date()),
                "symbol": p.universe_primary,
                "spot": spot,
                "strike": strike,
                "expiry": str(expiry),
                "entry_ce": ce,
                "entry_pe": pe,
                "entry_straddle": entry_straddle,
                "qty": qty,
                "lots": lots,
                "lot_size": lot,
                "sl_premium": sl_premium,
                "trade_score": fr.trade_score,
                "scores": fr.scores,
                "iv": iv,
                "margin_util_pct": margin_proxy / capital * 100.0 if capital else 0.0,
                "pt1_hit": False,
                "max_high": spot,
                "min_low": spot,
            }

        # Force flat if still open
        if open_trade is not None:
            last_ts = df.index[-1]
            last = df.iloc[-1]
            ce, pe = self._mark_premiums(float(last["close"]), open_trade, last_ts, float(last["vix"]) / 100.0)
            self._close_trade(open_trade, last_ts, ce, pe, capital_ref=capital, reason="EOD_FORCE")
            capital, day_pnl, week_pnl, day_loss_count = self._apply_close(
                open_trade, capital, day_pnl, week_pnl, day_loss_count, trades
            )

        if current_day is not None:
            equity_curve.append(capital)
            equity_days.append(str(current_day.date()))

        period_start = str(df.index[0].date()) if len(df) else ""
        period_end = str(df.index[-1].date()) if len(df) else ""
        metrics = compute_metrics(
            trades,
            equity_curve=equity_curve,
            initial_capital=capital0,
            period_start=period_start,
            period_end=period_end,
            traded_bars=traded_bars,
            total_bars=len(df),
            filter_pass_days=filter_pass_days,
            candidate_days=candidate_days,
        )
        return {
            "run_id": f"arass-{uuid.uuid4().hex[:10]}",
            "period_start": period_start,
            "period_end": period_end,
            "trades": trades,
            "equity_curve": equity_curve,
            "equity_days": equity_days,
            "metrics": metrics,
            "filter_stats": {
                "candidate_days": candidate_days,
                "filter_pass_days": filter_pass_days,
                "pass_rate_pct": (filter_pass_days / candidate_days * 100.0) if candidate_days else 0.0,
            },
            "paused_months": paused_months,
            "final_capital": capital,
        }

    def _mark_premiums(
        self,
        spot: float,
        trade: Dict[str, Any],
        ts: pd.Timestamp,
        iv: float,
        *,
        field: str = "close",
    ):
        p = self.params
        expiry = pd.Timestamp(trade["expiry"])
        strike = float(trade["strike"])
        if not p.use_synthetic_premiums and self.options_store is not None:
            hit = self.options_store.straddle(
                symbol=str(trade.get("symbol") or p.universe_primary),
                asof=ts,
                expiry=expiry,
                strike=strike,
                field=field,
            )
            if hit is not None:
                self._options_hits += 1
                return hit
            self._options_misses += 1
        tte = years_to_expiry(ts, expiry)
        ce = black_scholes_price(spot, strike, tte, iv, p.risk_free_rate, "CE")
        pe = black_scholes_price(spot, strike, tte, iv, p.risk_free_rate, "PE")
        return ce, pe

    def _close_trade(self, trade: Dict[str, Any], ts, ce: float, pe: float, capital_ref: float, reason: str):
        p = self.params
        cost = estimate_straddle_round_trip_cost(
            entry_ce=float(trade["entry_ce"]),
            entry_pe=float(trade["entry_pe"]),
            exit_ce=ce,
            exit_pe=pe,
            qty=int(trade["qty"]),
            params=p,
        )
        entry_straddle = float(trade["entry_straddle"])
        exit_straddle = ce + pe
        pnl_gross = (entry_straddle - exit_straddle) * int(trade["qty"])
        pnl_net = pnl_gross - cost.total
        trade.update(
            {
                "exit_time": str(ts),
                "exit_ce": ce,
                "exit_pe": pe,
                "exit_straddle": exit_straddle,
                "exit_reason": reason,
                "pnl_gross": pnl_gross,
                "pnl_net": pnl_net,
                "brokerage": cost.brokerage,
                "slippage": cost.slippage,
                "charges_total": cost.total,
            }
        )

    def _apply_close(self, trade, capital, day_pnl, week_pnl, day_loss_count, trades):
        pnl = float(trade["pnl_net"])
        capital = capital + pnl
        day_pnl = day_pnl + pnl
        week_pnl = week_pnl + pnl
        if pnl <= 0:
            day_loss_count += 1
        trades.append(dict(trade))
        return capital, day_pnl, week_pnl, day_loss_count


def run_arass_quick(
    panel: pd.DataFrame,
    params: ArassParams = ARASS_PARAMS,
) -> Dict[str, Any]:
    engine = ArassBacktestEngine(params=params)
    draft = build_arass_strategy_draft(params)
    result = engine.run(draft, {"panel": panel, "provenance": "quick"})
    return {
        "backtest_result": result,
        "arass_metrics": result.extras.get("arass_metrics", {}),
        "filter_stats": result.extras.get("filter_stats", {}),
    }
