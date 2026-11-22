"""
Bar-by-bar replay of the timed short straddle/strangle on 5m index bars.

Per day:
  1. At the first bar whose start >= entry time: ATM = spot (bar open) rounded to strike step.
     Optionally buy wings, then sell CE @ ATM+pts and PE @ ATM-pts.
  2. Each later bar: per-leg SL check using the *adverse* intrabar spot (bar high for the short
     CE, bar low for the short PE). A stop fills at max(trigger, price at bar open) + slippage,
     so gaps through the stop are paid in full. With wings, the matching wing is sold too.
     "Trail SL to cost" then moves the surviving short leg's stop to its entry price.
  3. Position MTM at bar close vs target / max loss -> exit everything at that close.
  4. Hard exit at the first bar starting at/after exit time (bar open).

Prices are synthetic (see pricing.py). All P&L is net of costs and slippage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from research.timed_straddle.costs import fill_cost
from research.timed_straddle.profit_lock import ProfitLockTracker, mtm_exit_reason, needs_mtm
from research.timed_straddle.params import TimedStraddleParams
from research.timed_straddle.pricing import IVCalibration, bs_price, years_to_expiry


@dataclass
class Leg:
    opt: str            # CE / PE
    strike: float
    side: int           # -1 short, +1 long
    entry: float
    stop: Optional[float] = None
    exit: Optional[float] = None
    exit_reason: str = ""
    costs: float = 0.0

    @property
    def open(self) -> bool:
        return self.exit is None

    def pnl_points(self, mark: float) -> float:
        px = self.exit if self.exit is not None else mark
        return (px - self.entry) * self.side


@dataclass
class DayResult:
    date: pd.Timestamp
    expiry: pd.Timestamp
    dte: int
    spot_entry: float
    atm: float
    vix_entry: float
    entry_premium: float          # short CE+PE credit (points)
    gross_points: float
    pnl: float                    # INR net of costs
    costs: float
    exit_reason: str
    legs: List[Dict] = field(default_factory=list)


class TimedStraddleEngine:
    def __init__(self, params: TimedStraddleParams, calibration: Optional[IVCalibration] = None):
        self.p = params
        self.cal = calibration or IVCalibration.identity()

    # ------------------------------------------------------------------ pricing
    def _px(self, opt: str, strike: float, spot: float, vix: float, ts: pd.Timestamp, expiry: pd.Timestamp) -> float:
        iv = self.cal.iv(vix, opt, ts, expiry, spot, strike)
        return bs_price(spot, strike, years_to_expiry(ts, expiry), iv, self.p.risk_free_rate, opt)

    def _fill(self, leg: Leg, price: float, side: str) -> float:
        """Apply slippage adversely; book costs on the leg. Returns executed price."""
        slip = self.p.slip
        px = price - slip if side == "SELL" else price + slip
        px = max(px, 0.05)
        leg.costs += fill_cost(px, self.p.qty, side, self.p.brokerage_per_order)
        return px

    # ------------------------------------------------------------------ run
    def run(self, panel: pd.DataFrame, expiry_map: Dict[pd.Timestamp, pd.Timestamp]) -> pd.DataFrame:
        results: List[DayResult] = []
        for day, bars in panel.groupby(panel.index.normalize()):
            if day.weekday() not in self.p.trade_weekdays:
                continue
            expiry = expiry_map.get(day)
            if expiry is None:
                continue
            dte = (expiry - day).days
            if self.p.max_dte is not None and dte > self.p.max_dte:
                continue
            r = self._run_day(day, bars, expiry, dte)
            if r is not None:
                results.append(r)
        return pd.DataFrame([r.__dict__ for r in results])

    def _run_day(self, day, bars: pd.DataFrame, expiry, dte) -> Optional[DayResult]:
        p = self.p
        hm = bars.index.hour * 60 + bars.index.minute
        entry_min = p.entry_hm[0] * 60 + p.entry_hm[1]
        exit_min = p.exit_hm[0] * 60 + p.exit_hm[1]
        entry_pos = np.flatnonzero(hm >= entry_min)
        if len(entry_pos) == 0:
            return None
        i0 = int(entry_pos[0])
        if hm[i0] >= exit_min or len(bars) - i0 < 3:
            return None

        o, h, l, c, v = (bars[k].to_numpy() for k in ("open", "high", "low", "close", "vix"))
        idx = bars.index
        ts0, spot0, vix0 = idx[i0], o[i0], v[i0]
        step = p.strike_step
        atm = round(spot0 / step) * step
        ce_k, pe_k = atm + p.points_from_atm, atm - p.points_from_atm

        legs: List[Leg] = []
        wings: Dict[str, Leg] = {}
        if p.buy_wings:
            for opt, k in (("CE", ce_k + p.wing_points), ("PE", pe_k - p.wing_points)):
                leg = Leg(opt, k, +1, 0.0)
                leg.entry = self._fill(leg, self._px(opt, k, spot0, vix0, ts0, expiry), "BUY")
                wings[opt] = leg
                legs.append(leg)
        shorts: Dict[str, Leg] = {}
        for opt, k in (("CE", ce_k), ("PE", pe_k)):
            leg = Leg(opt, k, -1, 0.0)
            leg.entry = self._fill(leg, self._px(opt, k, spot0, vix0, ts0, expiry), "SELL")
            leg.stop = leg.entry * (1.0 + p.sl_pct / 100.0)
            shorts[opt] = leg
            legs.append(leg)
        credit = shorts["CE"].entry + shorts["PE"].entry
        lock = ProfitLockTracker(p.profit_lock)

        reason = "time"
        for i in range(i0 + 1, len(bars)):
            ts = idx[i]
            if hm[i] >= exit_min:
                self._close_all(legs, o[i], v[i], ts, expiry, "time")
                break

            # --- per-leg stops (adverse intrabar extreme)
            for opt, leg in shorts.items():
                if not leg.open:
                    continue
                adverse_spot = h[i] if opt == "CE" else l[i]
                worst = self._px(opt, leg.strike, adverse_spot, v[i], ts, expiry)
                if worst >= leg.stop:
                    at_open = self._px(opt, leg.strike, o[i], v[i], ts, expiry)
                    leg.exit = self._fill(leg, max(leg.stop, at_open), "BUY")
                    leg.exit_reason = "sl"
                    if p.sell_wing_on_stop and opt in wings and wings[opt].open:
                        w = wings[opt]
                        w.exit = self._fill(w, self._px(opt, w.strike, adverse_spot, v[i], ts, expiry), "SELL")
                        w.exit_reason = "sl_wing"
                    other = shorts["PE" if opt == "CE" else "CE"]
                    if p.trail_sl_to_cost and other.open:
                        other.stop = min(other.stop, other.entry)

            if not any(leg.open for leg in legs):
                reason = "all_sl"
                break

            # --- position MTM at bar close
            if needs_mtm(p):
                mtm = self._mtm(legs, c[i], v[i], ts, expiry)
                why = mtm_exit_reason(p, mtm, lock)
                if why:
                    self._close_all(legs, c[i], v[i], ts, expiry, why)
                    reason = why
                    break
        else:
            # ran out of bars before exit time: close at last close
            self._close_all(legs, c[-1], v[-1], idx[-1], expiry, "eod")
            reason = "eod"

        if any(leg.exit_reason == "sl" for leg in legs) and reason == "time":
            reason = "time_after_sl"
        gross = sum(leg.pnl_points(0.0) for leg in legs)
        costs = sum(leg.costs for leg in legs)
        return DayResult(
            date=day, expiry=expiry, dte=dte, spot_entry=spot0, atm=atm, vix_entry=vix0,
            entry_premium=credit, gross_points=gross, pnl=gross * p.qty - costs, costs=costs,
            exit_reason=reason,
            legs=[{"opt": lg.opt, "strike": lg.strike, "side": lg.side, "entry": round(lg.entry, 2),
                   "exit": round(lg.exit or 0.0, 2), "why": lg.exit_reason} for lg in legs],
        )

    def _mtm(self, legs: List[Leg], spot, vix, ts, expiry) -> float:
        pts = 0.0
        costs = 0.0
        for leg in legs:
            mark = leg.exit if not leg.open else self._px(leg.opt, leg.strike, spot, vix, ts, expiry)
            pts += (mark - leg.entry) * leg.side
            costs += leg.costs
        return pts * self.p.qty - costs

    def _close_all(self, legs: List[Leg], spot, vix, ts, expiry, why: str) -> None:
        for leg in legs:
            if leg.open:
                px = self._px(leg.opt, leg.strike, spot, vix, ts, expiry)
                leg.exit = self._fill(leg, px, "BUY" if leg.side < 0 else "SELL")
                leg.exit_reason = why
