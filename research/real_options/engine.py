"""
Real-price replay of the straddle / premium-strangle rules on 1-minute option bars (no pricing model).

Uses the same parameter objects as the synthetic backtester (TimedStraddleParams / PremiumStrangleParams),
so results are directly comparable. Per minute:

* Entry at the entry minute's bar OPEN (strikes chosen from spot / option prices at that moment).
* Short-leg stop: bar HIGH >= stop -> fill at max(stop, bar open) + slippage (gaps paid).
* Short-leg target (strangle ``leg_target_pct``): bar LOW <= target -> fill at target + slippage.
* Re-entries (strangle ``max_adjustments``): re-sell that side at the minute's close, strike whose real
  close best matches the surviving short leg's close.
* Position MTM / profit lock / target / max loss on minute CLOSES; hard exit at the exit minute's OPEN.
* No-trade minutes carry the previous close (store); a contract with no price at entry is not traded.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from research.real_options.store import DayData
from research.timed_straddle.costs import fill_cost
from research.timed_straddle.engine import DayResult, Leg
from research.timed_straddle.params import TimedStraddleParams
from research.timed_straddle.profit_lock import ProfitLockTracker, mtm_exit_reason, needs_mtm
from research.timed_straddle.strangle import PremiumStrangleParams

O, H, L, C = 0, 1, 2, 3
SESSION_START = 9 * 60 + 15


def _minute(hm) -> int:
    return hm[0] * 60 + hm[1] - SESSION_START


class RealLeg(Leg):
    def __init__(self, opt, strike, side, bars: np.ndarray):
        super().__init__(opt, strike, side, 0.0)
        self.bars = bars


class RealPriceEngine:
    def __init__(self, params: TimedStraddleParams):
        self.p = params
        self.is_strangle = isinstance(params, PremiumStrangleParams)

    # ------------------------------------------------------------------ fills
    def _fill(self, leg: Leg, price: float, side: str) -> float:
        px = price - self.p.slip if side == "SELL" else price + self.p.slip
        px = max(px, 0.05)
        leg.costs += fill_cost(px, self.p.qty, side, self.p.brokerage_per_order)
        return px

    @staticmethod
    def _px(bars: np.ndarray, i: int, field: int) -> float:
        v = bars[i, field]
        if np.isnan(v):  # before first trade: fall back to the nearest later close
            later = bars[i:, C]
            ok = np.flatnonzero(~np.isnan(later))
            return float(later[ok[0]]) if len(ok) else float("nan")
        return float(v)

    # ------------------------------------------------------------------ strike selection
    def _premium_pick(self, day: DayData, opt: str, atm: float, i: int, want: float,
                      lo: float, hi: float, beyond: Optional[float] = None) -> Optional[Tuple[float, np.ndarray, float]]:
        best = None
        for k in day.available(opt):
            if beyond is not None:
                if (opt == "CE" and k <= beyond) or (opt == "PE" and k >= beyond):
                    continue
            elif (opt == "CE" and k < atm) or (opt == "PE" and k > atm):
                continue  # shorts: ATM or OTM only (as in the synthetic engine)
            bars = day.series(k, opt)
            px = bars[i, O]
            if np.isnan(px) or not (lo <= px <= hi):
                continue
            if best is None or abs(px - want) < abs(best[2] - want):
                best = (float(k), bars, float(px))
        return best

    def _nearest_strike(self, day: DayData, opt: str, target: float) -> Optional[float]:
        av = day.available(opt)
        if not len(av):
            return None
        return float(av[np.argmin(np.abs(av - target))])

    # ------------------------------------------------------------------ run
    def run(self, days: Iterable[DayData]) -> pd.DataFrame:
        out: List[dict] = []
        for day in days:
            if pd.Timestamp(day.day).weekday() not in self.p.trade_weekdays:
                continue
            dte = (day.expiry - day.day).days
            if dte < 0 or (self.p.max_dte is not None and dte > self.p.max_dte):
                continue
            r = self._run_day(day, dte)
            if r is not None:
                out.append(r.__dict__)
        return pd.DataFrame(out)

    def _run_day(self, day: DayData, dte: int) -> Optional[DayResult]:
        p = self.p
        i0, i_exit = _minute(p.entry_hm), _minute(p.exit_hm)
        n = day.spot.shape[0]
        if not (0 <= i0 < n - 2) or i_exit <= i0:
            return None
        i_exit = min(i_exit, n - 1)
        spot0 = float(day.spot[i0, O])
        step = p.strike_step
        atm = round(spot0 / step) * step

        legs: List[RealLeg] = []
        shorts: Dict[str, RealLeg] = {}
        wings: Dict[str, RealLeg] = {}

        # --- choose shorts
        if self.is_strangle:
            picks = {o: self._premium_pick(day, o, atm, i0, p.target_premium, p.min_premium, p.max_premium)
                     for o in ("CE", "PE")}
            if picks["CE"] is None or picks["PE"] is None:
                return None
            short_strikes = {o: (picks[o][0], picks[o][1]) for o in ("CE", "PE")}
        else:
            short_strikes = {}
            for o, k in (("CE", atm + p.points_from_atm), ("PE", atm - p.points_from_atm)):
                bars = day.series(k, o)
                if bars is None or np.isnan(self._px(bars, i0, O)):
                    return None
                short_strikes[o] = (k, bars)

        # --- choose wings / hedges (bought first)
        wing_specs: List[Tuple[str, float]] = []
        if self.is_strangle and p.hedge_premium is not None:
            for o in ("CE", "PE"):
                w = self._premium_pick(day, o, atm, i0, p.hedge_premium, 0.0, 1e9, beyond=short_strikes[o][0])
                if w is not None:
                    wing_specs.append((o, w[0]))
        elif self.is_strangle and p.hedge_points is not None:
            for o, tgt in (("CE", atm + p.hedge_points), ("PE", atm - p.hedge_points)):
                k = self._nearest_strike(day, o, tgt)
                if k is not None:
                    wing_specs.append((o, k))
        elif not self.is_strangle and p.buy_wings:
            for o, tgt in (("CE", short_strikes["CE"][0] + p.wing_points), ("PE", short_strikes["PE"][0] - p.wing_points)):
                k = self._nearest_strike(day, o, tgt)
                if k is not None:
                    wing_specs.append((o, k))
        for o, k in wing_specs:
            bars = day.series(k, o)
            px = self._px(bars, i0, O)
            if math.isnan(px):
                continue
            w = RealLeg(o, k, +1, bars)
            w.entry = self._fill(w, px, "BUY")
            wings[o] = w
            legs.append(w)

        for o in ("CE", "PE"):
            k, bars = short_strikes[o]
            leg = RealLeg(o, k, -1, bars)
            leg.entry = self._fill(leg, self._px(bars, i0, O), "SELL")
            leg.stop = leg.entry * (1.0 + p.sl_pct / 100.0)
            shorts[o] = leg
            legs.append(leg)
        credit = shorts["CE"].entry + shorts["PE"].entry
        lock = ProfitLockTracker(getattr(p, "profit_lock", None))
        adjustments = 0
        max_adj = getattr(p, "max_adjustments", 0) if self.is_strangle else 0
        sell_wing_on_stop = (not self.is_strangle) and getattr(p, "sell_wing_on_stop", True)
        reason = "time"

        for i in range(i0 + 1, n):
            if i >= i_exit:
                self._close_all(legs, i, O, "time")
                break
            for o in ("CE", "PE"):
                leg = shorts.get(o)
                if leg is None or not leg.open:
                    continue
                bar = leg.bars[i]
                if np.isnan(bar[H]):
                    continue
                exited = None
                if bar[H] >= leg.stop:
                    leg.exit = self._fill(leg, max(leg.stop, float(bar[O])), "BUY")
                    leg.exit_reason = exited = "sl"
                elif self.is_strangle and p.leg_target_pct is not None:
                    tgt = leg.entry * (1.0 - p.leg_target_pct / 100.0)
                    if bar[L] <= tgt:
                        leg.exit = self._fill(leg, tgt, "BUY")
                        leg.exit_reason = exited = "target"
                if exited is None:
                    continue
                if exited == "sl" and sell_wing_on_stop and o in wings and wings[o].open:
                    w = wings[o]
                    w.exit = self._fill(w, self._px(w.bars, i, C), "SELL")
                    w.exit_reason = "sl_wing"
                other = shorts["PE" if o == "CE" else "CE"]
                if exited == "sl" and p.trail_sl_to_cost and other.open:
                    other.stop = min(other.stop, other.entry)
                if adjustments < max_adj and (exited == "sl" or p.adjust_on_target):
                    want = self._px(other.bars, i, C) if other.open else p.target_premium
                    spot_i = float(day.spot[i, C])
                    atm_i = round(spot_i / step) * step
                    pick = None
                    best = None
                    for k in day.available(o):
                        if (o == "CE" and k < atm_i) or (o == "PE" and k > atm_i):
                            continue
                        bars = day.series(k, o)
                        px = bars[i, C]
                        if np.isnan(px) or not (p.min_premium <= px <= p.max_premium):
                            continue
                        if best is None or abs(px - want) < abs(best - want):
                            best, pick = px, (k, bars)
                    if pick is not None:
                        new = RealLeg(o, float(pick[0]), -1, pick[1])
                        new.entry = self._fill(new, float(best), "SELL")
                        new.stop = new.entry * (1.0 + p.sl_pct / 100.0)
                        legs.append(new)
                        shorts[o] = new
                        adjustments += 1

            if not any(lg.open for lg in shorts.values()):
                self._close_all(legs, i, C, "all_sl")
                reason = "all_sl"
                break
            if needs_mtm(p):
                mtm = self._mtm(legs, i)
                why = mtm_exit_reason(p, mtm, lock)
                if why:
                    self._close_all(legs, i, C, why)
                    reason = why
                    break
        else:
            self._close_all(legs, n - 1, C, "eod")
            reason = "eod"

        if reason == "time" and any(lg.exit_reason == "sl" for lg in legs):
            reason = "time_after_sl"
        gross = sum((lg.exit - lg.entry) * lg.side for lg in legs)
        costs = sum(lg.costs for lg in legs)
        return DayResult(
            date=pd.Timestamp(day.day), expiry=pd.Timestamp(day.expiry), dte=dte, spot_entry=spot0, atm=atm,
            vix_entry=float("nan"), entry_premium=credit, gross_points=gross, pnl=gross * p.qty - costs,
            costs=costs, exit_reason=reason,
            legs=[{"opt": lg.opt, "strike": lg.strike, "side": lg.side, "entry": round(lg.entry, 2),
                   "exit": round(lg.exit or 0.0, 2), "why": lg.exit_reason} for lg in legs],
        )

    def _mtm(self, legs: List[RealLeg], i: int) -> float:
        pts = costs = 0.0
        for lg in legs:
            mark = lg.exit if not lg.open else self._px(lg.bars, i, C)
            pts += (mark - lg.entry) * lg.side
            costs += lg.costs
        return pts * self.p.qty - costs

    def _close_all(self, legs: List[RealLeg], i: int, field: int, why: str) -> None:
        for lg in legs:
            if lg.open:
                px = self._px(lg.bars, i, field)
                if math.isnan(px):
                    px = self._px(lg.bars, max(i - 1, 0), C)
                lg.exit = self._fill(lg, px, "BUY" if lg.side < 0 else "SELL")
                lg.exit_reason = why
