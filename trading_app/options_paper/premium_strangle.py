"""
Live paper version of the premium-based short strangle (research/timed_straddle/strangle.py),
including the expiry-day variant with premium-based hedges.

Phases: WAIT_ENTRY -> SELECT_SHORTS (quote candidate strikes) -> SELECT_HEDGES (quote wing
candidates, if hedging) -> READY -> OPEN -> DONE / SKIPPED.

Fills at the real quote (sell at bid, buy at ask). Short legs: stop on LTP >= entry x (1+sl%),
optional target on LTP <= entry x (1-target%). An exited short is not re-entered in this V1
(``max_adjustments`` is ignored here). Hedges are held until the position closes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from research.timed_straddle.profit_lock import needs_mtm
from research.timed_straddle.strangle import PremiumStrangleParams
from trading_app.options_paper.instruments import INDEX_TOKENS
from trading_app.options_paper.quotes import Quote
from trading_app.options_paper.straddle import ENTRY_GRACE_MIN, PaperLeg, TimedStraddlePaper

SHORT_SEARCH = range(-3, 13)    # strike offsets from ATM searched for shorts (ITM 3 .. OTM 12)
HEDGE_SEARCH = range(1, 25)     # strike offsets beyond each short searched for hedges


class PremiumStranglePaper(TimedStraddlePaper):
    strategy_id = "premium_strangle"
    p: PremiumStrangleParams

    # ------------------------------------------------------------------ tokens
    def required_tokens(self):
        nse = [INDEX_TOKENS[self.p.symbol], INDEX_TOKENS["INDIAVIX"]]
        if self.s.phase in ("SELECT_SHORTS", "SELECT_HEDGES"):
            return nse, [c[3] for c in self.s.extra.get("candidates", [])]
        return nse, [lg.token for lg in self.s.legs if lg.open]

    def _candidates(self, opt: str, base: float, offsets) -> List[Tuple[str, float, str, str]]:
        """[(opt, strike, symbol, token)] for strikes base +/- k*step that exist in the scrip master."""
        exp = date.fromisoformat(self.s.expiry)
        step = self.p.strike_step
        out = []
        for k in offsets:
            strike = base + k * step if opt == "CE" else base - k * step
            c = self.chain.get(self.p.symbol, exp, strike, opt)
            if c is not None:
                out.append((opt, strike, c.symbol, c.token))
        return out

    @staticmethod
    def _closest(cands, quotes: Dict[str, Quote], opt: str, want: float, lo: float = 0.0, hi: float = 1e9):
        best = None
        for o, strike, sym, tok in cands:
            q = quotes.get(tok)
            if o != opt or q is None or q.ltp <= 0 or not (lo <= q.ltp <= hi):
                continue
            if best is None or abs(q.ltp - want) < abs(best[4] - want):
                best = (o, strike, sym, tok, q.ltp)
        return best

    # ------------------------------------------------------------------ main step
    def on_tick(self, now: datetime, quotes: Dict[str, Quote]) -> None:
        if self.done:
            return
        spot_q = quotes.get(INDEX_TOKENS[self.p.symbol])
        vix_q = quotes.get(INDEX_TOKENS["INDIAVIX"])
        if spot_q is None or spot_q.ltp <= 0:
            return
        spot, vix = spot_q.ltp, (vix_q.ltp if vix_q else None)
        m = self._mins(now)
        entry_m = self.p.entry_hm[0] * 60 + self.p.entry_hm[1]
        exit_m = self.p.exit_hm[0] * 60 + self.p.exit_hm[1]

        if self.s.phase in ("WAIT_ENTRY", "SELECT_SHORTS", "SELECT_HEDGES", "READY"):
            if m < entry_m:
                return
            if m >= exit_m or m > entry_m + ENTRY_GRACE_MIN:
                return self._skip("entry_window_missed")

        if self.s.phase == "WAIT_ENTRY":
            exp = self.chain.nearest_expiry(self.p.symbol, self.today)
            if exp is None:
                return self._skip("no_expiry_in_scrip_master")
            if self.p.max_dte is not None and (exp - self.today).days > self.p.max_dte:
                return self._skip(f"not_trading_day_dte{(exp - self.today).days}")
            step = self.p.strike_step
            atm = round(spot / step) * step
            self.s.expiry, self.s.atm, self.s.spot_entry = exp.isoformat(), atm, spot
            cands = self._candidates("CE", atm, SHORT_SEARCH) + self._candidates("PE", atm, SHORT_SEARCH)
            if not cands:
                return self._skip("no_short_candidates")
            self.s.extra = {"candidates": cands}
            self.s.phase = "SELECT_SHORTS"
            self.ledger.event("select_shorts", expiry=self.s.expiry, atm=atm, n=len(cands))
            self._persist()
            return

        if self.s.phase == "SELECT_SHORTS":
            cands = self.s.extra["candidates"]
            lo, hi = self.p.min_premium, self.p.max_premium
            picks = {o: self._closest(cands, quotes, o, self.p.target_premium, lo, hi) for o in ("CE", "PE")}
            if picks["CE"] is None or picks["PE"] is None:
                return  # quotes incomplete or nothing in the band yet; retry next poll (within grace)
            self.s.extra["shorts"] = picks
            self.ledger.event("shorts_selected", **{o: f"{p_[2]}@{p_[4]}" for o, p_ in picks.items()})
            if self.p.hedge_premium is None:
                self._build_legs(picks, None)
            else:
                hc = (self._candidates("CE", picks["CE"][1], HEDGE_SEARCH)
                      + self._candidates("PE", picks["PE"][1], HEDGE_SEARCH))
                self.s.extra["candidates"] = hc
                self.s.phase = "SELECT_HEDGES"
            self._persist()
            return

        if self.s.phase == "SELECT_HEDGES":
            hc = self.s.extra["candidates"]
            wings = {o: self._closest(hc, quotes, o, self.p.hedge_premium) for o in ("CE", "PE")}
            if wings["CE"] is None or wings["PE"] is None:
                return
            self.ledger.event("hedges_selected", **{o: f"{w[2]}@{w[4]}" for o, w in wings.items()})
            self._build_legs(self.s.extra["shorts"], wings)
            self._persist()
            return

        if self.s.phase == "READY":
            if any(lg.token not in quotes for lg in self.s.legs):
                return
            self._enter(spot, vix, now, quotes)
            self._persist()
            return

        if self.s.phase != "OPEN":
            return
        if m >= exit_m:
            self._close_all(quotes, spot, vix, now, "time")
            return

        for leg in [lg for lg in self.s.legs if lg.side < 0 and lg.open]:
            q = quotes.get(leg.token)
            if q is None:
                continue
            if q.ltp >= leg.stop:
                self._fill(leg, q, "BUY", spot, vix, now, False, "sl")
                if self.p.trail_sl_to_cost:
                    for other in self.s.legs:
                        if other.side < 0 and other.open:
                            other.stop = min(other.stop, other.entry)
            elif self.p.leg_target_pct is not None and q.ltp <= leg.entry * (1 - self.p.leg_target_pct / 100.0):
                self._fill(leg, q, "BUY", spot, vix, now, False, "target")

        if not any(lg.open for lg in self.s.legs if lg.side < 0):
            self._close_all(quotes, spot, vix, now, "all_legs_out")  # sells remaining hedges
            return
        if needs_mtm(self.p):
            mtm = self._mtm(quotes)
            if mtm is not None and self._mtm_exit(mtm, quotes, spot, vix, now):
                return
        self._persist()

    # ------------------------------------------------------------------ helpers
    def _skip(self, reason: str) -> None:
        self.s.phase, self.s.exit_reason = "SKIPPED", reason
        self.ledger.event("skipped", reason=reason)
        self._persist()

    def _build_legs(self, shorts, wings) -> None:
        legs: List[PaperLeg] = []
        if wings:
            for o in ("CE", "PE"):
                w = wings[o]
                legs.append(PaperLeg(opt=o, strike=w[1], side=+1, token=w[3], symbol=w[2]))
        for o in ("CE", "PE"):
            sh = shorts[o]
            legs.append(PaperLeg(opt=o, strike=sh[1], side=-1, token=sh[3], symbol=sh[2]))
        self.s.legs = legs
        self.s.extra.pop("candidates", None)
        self.s.phase = "READY"
        self.ledger.event("legs_selected", expiry=self.s.expiry, legs=[lg.symbol for lg in legs])
