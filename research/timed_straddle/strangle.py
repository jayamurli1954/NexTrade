"""
Premium-based short strangle with premium-matching re-entries — research backtest.

Per day:
  1. At entry time, sell the CE and the PE whose synthetic premium is closest to ``target_premium``
     within [min_premium, max_premium] (searching OTM from ATM). Optional hedge wings at
     ATM ± ``hedge_points`` are bought first.
  2. Each short leg has its own stop (entry x (1 + sl_pct/100)) and optional target
     (entry x (1 - leg_target_pct/100)), checked like the straddle engine (adverse intrabar extreme).
  3. When a short leg exits (stop or target), that side is re-sold at the strike whose premium best
     matches the surviving short leg's current premium (or ``target_premium`` if none survives),
     up to ``max_adjustments`` re-entries per day. Optional stop-to-cost on the survivor.
  4. Position MTM target / max loss, then hard time exit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from research.timed_straddle.engine import DayResult, Leg, TimedStraddleEngine
from research.timed_straddle.profit_lock import ProfitLockTracker, mtm_exit_reason, needs_mtm
from research.timed_straddle.params import TimedStraddleParams


@dataclass(frozen=True)
class PremiumStrangleParams(TimedStraddleParams):
    target_premium: float = 40.0
    min_premium: float = 20.0
    max_premium: float = 60.0
    max_search_steps: int = 40          # strikes searched OTM from ATM, per side
    leg_target_pct: Optional[float] = None   # e.g. 50 = buy back at half the premium (None = off)
    max_adjustments: int = 2            # premium-matching re-entries per day (0 = none)
    adjust_on_target: bool = True       # also re-enter after a leg hits its target
    hedge_points: Optional[float] = None    # buy wings at ATM +/- this (None = no hedge)
    hedge_premium: Optional[float] = None   # or: buy the wing whose premium is closest to this, beyond the shorts
    sl_pct: float = 40.0


class PremiumStrangleEngine(TimedStraddleEngine):
    p: PremiumStrangleParams

    # ------------------------------------------------------------------ strike selection
    def pick_strike(self, opt: str, spot: float, vix: float, ts, expiry, want: float,
                    exclude: Tuple[float, ...] = ()) -> Optional[Tuple[float, float]]:
        """Return (strike, model premium) closest to ``want`` within [min, max]; OTM side only."""
        p, step = self.p, self.p.strike_step
        atm = round(spot / step) * step
        best: Optional[Tuple[float, float]] = None
        for k in range(0, p.max_search_steps + 1):
            strike = atm + k * step if opt == "CE" else atm - k * step
            if strike in exclude:
                continue
            px = self._px(opt, strike, spot, vix, ts, expiry)
            if px < p.min_premium:
                break  # further OTM only gets cheaper
            if px > p.max_premium:
                continue
            if best is None or abs(px - want) < abs(best[1] - want):
                best = (strike, px)
        return best

    def pick_wing(self, opt: str, short_strike: float, spot: float, vix: float, ts, expiry,
                  want: float) -> Tuple[float, float]:
        """Cheapest-side wing: strike beyond the short whose premium is closest to ``want``."""
        step = self.p.strike_step
        best: Optional[Tuple[float, float]] = None
        for k in range(1, 4 * self.p.max_search_steps + 1):
            strike = short_strike + k * step if opt == "CE" else short_strike - k * step
            px = self._px(opt, strike, spot, vix, ts, expiry)
            if best is None or abs(px - want) < abs(best[1] - want):
                best = (strike, px)
            if px < want * 0.5:
                break
        return best

    def _sell(self, opt: str, strike: float, spot, vix, ts, expiry) -> Leg:
        leg = Leg(opt, strike, -1, 0.0)
        leg.entry = self._fill(leg, self._px(opt, strike, spot, vix, ts, expiry), "SELL")
        leg.stop = leg.entry * (1.0 + self.p.sl_pct / 100.0)
        return leg

    # ------------------------------------------------------------------ day loop
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

        picks = {opt: self.pick_strike(opt, spot0, vix0, ts0, expiry, p.target_premium) for opt in ("CE", "PE")}
        if picks["CE"] is None or picks["PE"] is None:
            return None  # no strike in the premium band today (e.g. expiry-day afternoon)

        legs: List[Leg] = []
        wings: Dict[str, Leg] = {}
        if p.hedge_points is not None or p.hedge_premium is not None:
            if p.hedge_premium is not None:
                wing_strikes = [(o_, self.pick_wing(o_, picks[o_][0], spot0, vix0, ts0, expiry, p.hedge_premium)[0])
                                for o_ in ("CE", "PE")]
            else:
                wing_strikes = [("CE", atm + p.hedge_points), ("PE", atm - p.hedge_points)]
            for opt, k in wing_strikes:
                leg = Leg(opt, k, +1, 0.0)
                leg.entry = self._fill(leg, self._px(opt, k, spot0, vix0, ts0, expiry), "BUY")
                wings[opt] = leg
                legs.append(leg)
        shorts: Dict[str, Leg] = {}
        for opt in ("CE", "PE"):
            leg = self._sell(opt, picks[opt][0], spot0, vix0, ts0, expiry)
            shorts[opt] = leg
            legs.append(leg)
        credit = shorts["CE"].entry + shorts["PE"].entry
        adjustments = 0
        lock = ProfitLockTracker(p.profit_lock)
        reason = "time"

        for i in range(i0 + 1, len(bars)):
            ts = idx[i]
            if hm[i] >= exit_min:
                self._close_all(legs, o[i], v[i], ts, expiry, "time")
                break

            for opt in ("CE", "PE"):
                leg = shorts.get(opt)
                if leg is None or not leg.open:
                    continue
                adverse_spot = h[i] if opt == "CE" else l[i]
                favour_spot = l[i] if opt == "CE" else h[i]
                exited_why = None
                worst = self._px(opt, leg.strike, adverse_spot, v[i], ts, expiry)
                if worst >= leg.stop:
                    at_open = self._px(opt, leg.strike, o[i], v[i], ts, expiry)
                    leg.exit = self._fill(leg, max(leg.stop, at_open), "BUY")
                    leg.exit_reason = exited_why = "sl"
                elif p.leg_target_pct is not None:
                    tgt = leg.entry * (1.0 - p.leg_target_pct / 100.0)
                    best = self._px(opt, leg.strike, favour_spot, v[i], ts, expiry)
                    if best <= tgt:
                        leg.exit = self._fill(leg, tgt, "BUY")
                        leg.exit_reason = exited_why = "target"
                if exited_why is None:
                    continue

                other = shorts["PE" if opt == "CE" else "CE"]
                if exited_why == "sl" and p.trail_sl_to_cost and other.open:
                    other.stop = min(other.stop, other.entry)

                if adjustments < p.max_adjustments and (exited_why == "sl" or p.adjust_on_target):
                    want = (self._px(other.opt, other.strike, c[i], v[i], ts, expiry)
                            if other.open else p.target_premium)
                    pick = self.pick_strike(opt, c[i], v[i], ts, expiry, want, exclude=())
                    if pick is not None:
                        new = self._sell(opt, pick[0], c[i], v[i], ts, expiry)
                        legs.append(new)
                        shorts[opt] = new
                        adjustments += 1

            open_shorts = [lg for lg in shorts.values() if lg.open]
            if not open_shorts:
                self._close_all(legs, c[i], v[i], ts, expiry, "all_legs_out")
                reason = "all_legs_out"
                break

            if needs_mtm(p):
                mtm = self._mtm(legs, c[i], v[i], ts, expiry)
                why = mtm_exit_reason(p, mtm, lock)
                if why:
                    self._close_all(legs, c[i], v[i], ts, expiry, why)
                    reason = why
                    break
        else:
            self._close_all(legs, c[-1], v[-1], idx[-1], expiry, "eod")
            reason = "eod"

        if reason == "time" and adjustments:
            reason = "time_after_adjust"
        gross = sum(leg.pnl_points(0.0) for leg in legs)
        costs = sum(leg.costs for leg in legs)
        return DayResult(
            date=day, expiry=expiry, dte=dte, spot_entry=spot0, atm=atm, vix_entry=vix0,
            entry_premium=credit, gross_points=gross, pnl=gross * p.qty - costs, costs=costs,
            exit_reason=reason,
            legs=[{"opt": lg.opt, "strike": lg.strike, "side": lg.side, "entry": round(lg.entry, 2),
                   "exit": round(lg.exit or 0.0, 2), "why": lg.exit_reason} for lg in legs],
        )
