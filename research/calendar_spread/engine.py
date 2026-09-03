"""
CAL-2 calendar / rollover spread research engine.

Daily spot + OptionsStore premiums. Research-only (OIE-001 / freeze safe).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd

from research.arass.indicators import nifty_lot_size
from research.arass.options_store import OptionsStore
from research.calendar_spread.costs import (
    calendar_pnl_pts,
    estimate_calendar_311_round_trip_cost,
)
from research.calendar_spread.definition import CAL_PARAMS, CalendarSpreadParams
from research.calendar_spread.expiries import expiries_on_or_after, pick_expiry_triplet
from research.calendar_spread.metrics import compute_calendar_metrics
from research.calendar_spread.signals import premium_differential
from research.calendar_spread.zone import (
    overnight_gap_pct,
    select_strike,
    zone_bounds,
    zone_lean,
)

logger = logging.getLogger("CalendarSpreadEngine")


class CalendarSpreadEngine:
    engine_name = "NEXTRADE_CALENDAR_SPREAD_RESEARCH_V1"

    def __init__(self, params: CalendarSpreadParams = CAL_PARAMS):
        self.params = params

    def run(
        self,
        spot: pd.DataFrame,
        options: OptionsStore,
        *,
        initial_capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        p = self.params
        capital0 = float(initial_capital if initial_capital is not None else p.initial_capital)
        df = spot.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df.columns = [str(c).lower() for c in df.columns]
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                raise ValueError(f"Spot panel missing column: {col}")

        # Daily bars only
        daily = (
            df.groupby(df.index.normalize())
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
            )
            .dropna()
        )
        zh, zl = zone_bounds(daily["high"], daily["low"], p.zone_lookback)
        daily["zone_high"] = zh
        daily["zone_low"] = zl
        daily["prior_close"] = daily["close"].shift(1)

        opt_df = options.df
        if opt_df is not None and not opt_df.empty:
            opt_df = opt_df[opt_df["symbol"] == str(p.symbol).upper()].copy()

        capital = capital0
        equity: List[float] = [capital]
        equity_days: List[str] = []
        trades: List[Dict[str, Any]] = []
        open_pos: Optional[Dict[str, Any]] = None

        pts_candidates = 0
        pts_hits = 0
        candidate_diffs: List[float] = []
        skip_gap = skip_zone = skip_expiry = skip_prem = 0
        lookup_miss = 0

        for day, row in daily.iterrows():
            day = pd.Timestamp(day).normalize()
            day_s = day.strftime("%Y-%m-%d")
            spot_px = float(row["close"])
            open_px = float(row["open"])
            lot = nifty_lot_size(day, default=p.lot_default)

            # --- manage open ---
            if open_pos is not None:
                marks = self._mark_legs(options, day, open_pos)
                if marks is None:
                    lookup_miss += 1
                else:
                    m_near, m_next, m_far = marks
                    pts = calendar_pnl_pts(
                        entry_near=open_pos["entry_near"],
                        entry_next=open_pos["entry_next"],
                        entry_far=open_pos["entry_far"],
                        mark_near=m_near,
                        mark_next=m_next,
                        mark_far=m_far,
                        far_lots=p.far_lots,
                        near_lots=p.near_lots,
                        next_lots=p.next_lots,
                    )
                    diff = premium_differential(
                        near=m_near, nxt=m_next, far=m_far, mode=p.diff_mode
                    )
                    reason = None
                    if day >= pd.Timestamp(open_pos["near_expiry"]).normalize():
                        reason = "NEAR_EXPIRY"
                    elif pts <= float(p.stop_pts_lot_equiv):
                        reason = "STOP_PTS"
                    elif diff < float(p.exit_diff_below):
                        reason = "DIFF_MEAN_REVERT"
                    if reason:
                        closed = self._close_trade(
                            open_pos,
                            exit_day=day_s,
                            exit_near=m_near,
                            exit_next=m_next,
                            exit_far=m_far,
                            lot=lot,
                            reason=reason,
                            params=p,
                        )
                        capital += float(closed["pnl_net"])
                        trades.append(closed)
                        open_pos = None

            equity.append(capital)
            equity_days.append(day_s)

            if open_pos is not None:
                continue

            # --- entry filters ---
            prior = row.get("prior_close")
            if prior is None or (isinstance(prior, float) and prior != prior):
                continue
            gap = overnight_gap_pct(open_px, float(prior))
            if gap >= float(p.gap_skip_pct):
                skip_gap += 1
                continue

            zhi = row.get("zone_high")
            zlo = row.get("zone_low")
            if zhi != zhi or zlo != zlo:
                continue
            lean = zone_lean(spot_px, float(zhi), float(zlo))
            if lean is None:
                skip_zone += 1
                continue

            strike = select_strike(
                spot_px,
                lean,
                zone_high=float(zhi),
                zone_low=float(zlo),
                strike_step=p.strike_step,
                offset_toward_extreme=p.zone_strike_offset,
            )

            exps = expiries_on_or_after(opt_df, symbol=p.symbol, asof=day)
            trip = pick_expiry_triplet(exps, asof=day, params=p)
            if trip is None:
                skip_expiry += 1
                continue

            prem = self._lookup_triplet(
                options,
                day=day,
                strike=strike,
                lean=lean,
                near=trip.near,
                nxt=trip.next_weekly,
                far=trip.far,
            )
            if prem is None:
                skip_prem += 1
                lookup_miss += 1
                continue

            near_px, next_px, far_px = prem
            diff = premium_differential(
                near=near_px, nxt=next_px, far=far_px, mode=p.diff_mode
            )
            pts_candidates += 1
            candidate_diffs.append(diff)
            if not (float(p.pts_band_lo) <= diff <= float(p.pts_band_hi)):
                continue
            pts_hits += 1

            open_pos = {
                "trade_id": f"cal_{uuid.uuid4().hex[:8]}",
                "entry_date": day_s,
                "symbol": p.symbol,
                "lean": lean,
                "strike": float(strike),
                "lot_size": int(lot),
                "diff_mode": p.diff_mode,
                "near_expiry": trip.near.strftime("%Y-%m-%d"),
                "next_expiry": trip.next_weekly.strftime("%Y-%m-%d"),
                "far_expiry": trip.far.strftime("%Y-%m-%d"),
                "near_dte": trip.near_dte,
                "next_dte": trip.next_dte,
                "far_dte": trip.far_dte,
                "entry_near": float(near_px),
                "entry_next": float(next_px),
                "entry_far": float(far_px),
                "entry_diff": float(diff),
                "spot": spot_px,
                "gap_pct": round(gap, 4),
            }

        # Force flat at end
        if open_pos is not None:
            last_day = pd.Timestamp(daily.index[-1]).normalize()
            marks = self._mark_legs(options, last_day, open_pos)
            if marks is not None:
                m_near, m_next, m_far = marks
                closed = self._close_trade(
                    open_pos,
                    exit_day=last_day.strftime("%Y-%m-%d"),
                    exit_near=m_near,
                    exit_next=m_next,
                    exit_far=m_far,
                    lot=int(open_pos["lot_size"]),
                    reason="END_OF_SAMPLE",
                    params=p,
                )
                capital += float(closed["pnl_net"])
                trades.append(closed)
                equity.append(capital)
                equity_days.append(last_day.strftime("%Y-%m-%d"))

        metrics = compute_calendar_metrics(
            trades,
            equity_curve=equity,
            initial_capital=capital0,
            pts_band_hits=pts_hits,
            pts_band_candidates=pts_candidates,
        )
        period_start = daily.index[0].strftime("%Y-%m-%d") if len(daily) else None
        period_end = daily.index[-1].strftime("%Y-%m-%d") if len(daily) else None
        return {
            "run_id": f"cal2_{uuid.uuid4().hex[:10]}",
            "engine_name": self.engine_name,
            "params_version": p.version,
            "period_start": period_start,
            "period_end": period_end,
            "trades": trades,
            "equity_curve": equity,
            "equity_days": equity_days,
            "metrics": metrics.to_dict(),
            "filter_stats": {
                "pts_band_candidates": pts_candidates,
                "pts_band_hits": pts_hits,
                "pts_band_lo": float(p.pts_band_lo),
                "pts_band_hi": float(p.pts_band_hi),
                "diff_mode": p.diff_mode,
                "candidate_diff_min": round(min(candidate_diffs), 2) if candidate_diffs else None,
                "candidate_diff_median": (
                    round(float(pd.Series(candidate_diffs).median()), 2) if candidate_diffs else None
                ),
                "candidate_diff_max": round(max(candidate_diffs), 2) if candidate_diffs else None,
                "skip_gap": skip_gap,
                "skip_zone": skip_zone,
                "skip_expiry": skip_expiry,
                "skip_premium": skip_prem,
                "lookup_miss": lookup_miss,
            },
            "notes": (
                "CAL-2 research only. Structure 3:1:1. "
                "Not certified for paper/live. Freeze-safe."
            ),
        }

    def _lookup_triplet(
        self,
        store: OptionsStore,
        *,
        day: pd.Timestamp,
        strike: float,
        lean: str,
        near: pd.Timestamp,
        nxt: pd.Timestamp,
        far: pd.Timestamp,
    ) -> Optional[tuple]:
        p = self.params
        kwargs = dict(
            symbol=p.symbol,
            asof=day,
            strike=strike,
            option_type=lean,
            field="close",
            strike_step=p.strike_step,
            allow_nearest_strike=True,
            allow_nearest_expiry=True,
            asof_policy="on_or_before",
        )
        n = store.lookup(expiry=near, **kwargs)
        x = store.lookup(expiry=nxt, **kwargs)
        f = store.lookup(expiry=far, **kwargs)
        if n is None or x is None or f is None:
            return None
        return float(n), float(x), float(f)

    def _mark_legs(
        self,
        store: OptionsStore,
        day: pd.Timestamp,
        pos: Dict[str, Any],
    ) -> Optional[tuple]:
        return self._lookup_triplet(
            store,
            day=day,
            strike=float(pos["strike"]),
            lean=str(pos["lean"]),
            near=pd.Timestamp(pos["near_expiry"]),
            nxt=pd.Timestamp(pos["next_expiry"]),
            far=pd.Timestamp(pos["far_expiry"]),
        )

    def _close_trade(
        self,
        pos: Dict[str, Any],
        *,
        exit_day: str,
        exit_near: float,
        exit_next: float,
        exit_far: float,
        lot: int,
        reason: str,
        params: CalendarSpreadParams,
    ) -> Dict[str, Any]:
        pts = calendar_pnl_pts(
            entry_near=pos["entry_near"],
            entry_next=pos["entry_next"],
            entry_far=pos["entry_far"],
            mark_near=exit_near,
            mark_next=exit_next,
            mark_far=exit_far,
            far_lots=params.far_lots,
            near_lots=params.near_lots,
            next_lots=params.next_lots,
        )
        pnl_gross = float(pts) * float(lot)
        cost = estimate_calendar_311_round_trip_cost(
            entry_near=pos["entry_near"],
            entry_next=pos["entry_next"],
            entry_far=pos["entry_far"],
            exit_near=exit_near,
            exit_next=exit_next,
            exit_far=exit_far,
            lot_size=lot,
            params=params,
        )
        pnl_net = pnl_gross - cost.total
        exit_diff = premium_differential(
            near=exit_near,
            nxt=exit_next,
            far=exit_far,
            mode=params.diff_mode,
        )
        return {
            **pos,
            "exit_date": exit_day,
            "exit_near": float(exit_near),
            "exit_next": float(exit_next),
            "exit_far": float(exit_far),
            "exit_diff": round(exit_diff, 2),
            "pnl_pts": round(float(pts), 2),
            "pnl_gross": round(pnl_gross, 2),
            "charges": round(cost.total, 2),
            "charges_breakdown": cost.to_dict(),
            "pnl_net": round(pnl_net, 2),
            "exit_reason": reason,
            "status": "CLOSED",
        }
