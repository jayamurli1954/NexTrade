"""
Live paper version of the timed short straddle/strangle (same rules as research/timed_straddle).

Fills are simulated at the *real* quote: sells at best bid, buys at best ask. Stops trigger on
LTP >= stop (like an exchange SL trigger) and fill at the ask on that poll, so the gap between
the stop and the actual fill is measured, not assumed. Every fill also records the backtest
model's price for the same moment (when VIX is available) to measure model error/slippage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from research.timed_straddle.profit_lock import needs_mtm
from research.timed_straddle.costs import fill_cost
from research.timed_straddle.params import TimedStraddleParams
from trading_app.options_paper.instruments import INDEX_TOKENS, OptionChainIndex, OptionContract
from trading_app.options_paper.ledger import PaperLedger
from trading_app.options_paper.quotes import Quote

ModelPricer = Callable[[str, float, float, float, datetime, date], float]

ENTRY_GRACE_MIN = 15  # give up on entry if quotes never arrive within this many minutes


@dataclass
class PaperLeg:
    opt: str
    strike: float
    side: int                 # -1 short, +1 long
    token: str
    symbol: str
    entry: float = 0.0
    stop: Optional[float] = None
    exit: Optional[float] = None
    exit_reason: str = ""
    charges: float = 0.0
    model_entry: Optional[float] = None
    model_exit: Optional[float] = None

    @property
    def open(self) -> bool:
        return self.exit is None


@dataclass
class StraddleState:
    phase: str = "WAIT_ENTRY"       # WAIT_ENTRY -> OPEN -> DONE / SKIPPED
    expiry: Optional[str] = None
    atm: Optional[float] = None
    spot_entry: Optional[float] = None
    legs: List[PaperLeg] = field(default_factory=list)
    exit_reason: str = ""
    extra: Dict = field(default_factory=dict)   # strategy-specific state (e.g. strike candidates)


class TimedStraddlePaper:
    strategy_id = "timed_straddle"

    def __init__(self, params: TimedStraddleParams, chain: OptionChainIndex, ledger: PaperLedger,
                 today: date, model_pricer: Optional[ModelPricer] = None, name: Optional[str] = None):
        self.name = name or f"{self.strategy_id}_{params.symbol.lower()}"
        self.p = params
        self.chain = chain
        self.ledger = ledger
        self.today = today
        self.model = model_pricer
        self.s = StraddleState()
        self._restore()

    # ------------------------------------------------------------------ persistence
    def _restore(self) -> None:
        st = self.ledger.load_state()
        if not st:
            return
        legs = [PaperLeg(**lg) for lg in st.pop("legs", [])]
        self.s = StraddleState(**st, legs=legs)
        self.ledger.event("resumed", phase=self.s.phase, legs=len(legs))

    def _persist(self) -> None:
        d = asdict(self.s)
        self.ledger.save_state(d)

    # ------------------------------------------------------------------ helpers
    @property
    def done(self) -> bool:
        return self.s.phase in ("DONE", "SKIPPED")

    def required_tokens(self):
        nse = [INDEX_TOKENS[self.p.symbol], INDEX_TOKENS["INDIAVIX"]]
        nfo = [lg.token for lg in self.s.legs if lg.open]
        return nse, nfo

    def _mins(self, now: datetime) -> int:
        return now.hour * 60 + now.minute

    def _model(self, leg: PaperLeg, spot: float, vix: Optional[float], now: datetime) -> Optional[float]:
        if self.model is None or not vix or not self.s.expiry:
            return None
        try:
            return round(self.model(leg.opt, leg.strike, spot, vix, now, date.fromisoformat(self.s.expiry)), 2)
        except Exception:
            return None

    def _fill(self, leg: PaperLeg, q: Quote, side: str, spot: float, vix: Optional[float], now: datetime,
              is_entry: bool, reason: str = "") -> None:
        px = q.sell_price if side == "SELL" else q.buy_price
        leg.charges += fill_cost(px, self.p.qty, side, self.p.brokerage_per_order)
        model_px = self._model(leg, spot, vix, now)
        if is_entry:
            leg.entry, leg.model_entry = px, model_px
        else:
            leg.exit, leg.exit_reason, leg.model_exit = px, reason, model_px
        self.ledger.event("fill", side=side, symbol=leg.symbol, price=px, ltp=q.ltp, bid=q.bid, ask=q.ask,
                          model=model_px, spot=spot, vix=vix, reason=reason or "entry", qty=self.p.qty)

    def _mtm(self, quotes: Dict[str, Quote]) -> Optional[float]:
        pts, charges = 0.0, 0.0
        for lg in self.s.legs:
            charges += lg.charges
            if lg.open:
                q = quotes.get(lg.token)
                if q is None:
                    return None
                mark = q.buy_price if lg.side < 0 else q.sell_price
            else:
                mark = lg.exit
            pts += (mark - lg.entry) * lg.side
        return pts * self.p.qty - charges

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

        if self.s.phase == "WAIT_ENTRY":
            if m < entry_m:
                return
            if m >= exit_m or m > entry_m + ENTRY_GRACE_MIN:
                self.s.phase, self.s.exit_reason = "SKIPPED", "entry_window_missed"
                self.ledger.event("skipped", reason=self.s.exit_reason)
                self._persist()
                return
            self._prepare_legs(spot)
            if self.s.phase == "SKIPPED":
                self._persist()
                return
            # need quotes for the new legs: ask caller to fetch again next poll
            missing = [lg for lg in self.s.legs if lg.token not in quotes]
            if missing:
                self._persist()
                return
            self._enter(spot, vix, now, quotes)
            self._persist()
            return

        if self.s.phase == "READY":
            missing = [lg for lg in self.s.legs if lg.token not in quotes]
            if missing:
                if m > entry_m + ENTRY_GRACE_MIN:
                    self.s.phase, self.s.exit_reason = "SKIPPED", "no_option_quotes"
                    self.ledger.event("skipped", reason=self.s.exit_reason)
                    self._persist()
                return
            self._enter(spot, vix, now, quotes)
            self._persist()
            return

        if self.s.phase != "OPEN":
            return

        if m >= exit_m:
            self._close_all(quotes, spot, vix, now, "time")
            return

        shorts = {lg.opt: lg for lg in self.s.legs if lg.side < 0}
        wings = {lg.opt: lg for lg in self.s.legs if lg.side > 0}
        for opt, leg in shorts.items():
            if not leg.open:
                continue
            q = quotes.get(leg.token)
            if q is None:
                continue
            if q.ltp >= leg.stop:
                self._fill(leg, q, "BUY", spot, vix, now, False, "sl")
                w = wings.get(opt)
                if w is not None and w.open and w.token in quotes:
                    self._fill(w, quotes[w.token], "SELL", spot, vix, now, False, "sl_wing")
                other = shorts["PE" if opt == "CE" else "CE"]
                if self.p.trail_sl_to_cost and other.open:
                    other.stop = min(other.stop, other.entry)
                    self.ledger.event("trail_to_cost", symbol=other.symbol, stop=other.stop)

        if not any(lg.open for lg in self.s.legs):
            self._finish("all_sl", spot, vix, now)
            return

        if needs_mtm(self.p):
            mtm = self._mtm(quotes)
            if mtm is not None and self._mtm_exit(mtm, quotes, spot, vix, now):
                return
        self._persist()

    # ------------------------------------------------------------------ phases
    def _prepare_legs(self, spot: float) -> None:
        exp = self.chain.nearest_expiry(self.p.symbol, self.today)
        if exp is None:
            self.s.phase, self.s.exit_reason = "SKIPPED", "no_expiry_in_scrip_master"
            self.ledger.event("skipped", reason=self.s.exit_reason)
            return
        dte = (exp - self.today).days
        if self.p.max_dte is not None and dte > self.p.max_dte:
            self.s.phase, self.s.exit_reason = "SKIPPED", f"not_trading_day_dte{dte}"
            self.ledger.event("skipped", reason=self.s.exit_reason, expiry=exp.isoformat())
            return
        step = self.p.strike_step
        atm = round(spot / step) * step
        ce_k, pe_k = atm + self.p.points_from_atm, atm - self.p.points_from_atm
        wanted = []
        if self.p.buy_wings:
            wanted += [("CE", ce_k + self.p.wing_points, +1), ("PE", pe_k - self.p.wing_points, +1)]
        wanted += [("CE", ce_k, -1), ("PE", pe_k, -1)]
        legs: List[PaperLeg] = []
        for opt, k, side in wanted:
            c: Optional[OptionContract] = self.chain.get(self.p.symbol, exp, k, opt)
            if c is None:
                self.s.phase, self.s.exit_reason = "SKIPPED", f"contract_missing_{opt}_{k:g}"
                self.ledger.event("skipped", reason=self.s.exit_reason)
                return
            legs.append(PaperLeg(opt=opt, strike=k, side=side, token=c.token, symbol=c.symbol))
        self.s.expiry, self.s.atm, self.s.spot_entry, self.s.legs = exp.isoformat(), atm, spot, legs
        self.s.phase = "READY"
        self.ledger.event("legs_selected", expiry=self.s.expiry, atm=atm, spot=spot,
                          legs=[lg.symbol for lg in legs])

    def _enter(self, spot: float, vix: Optional[float], now: datetime, quotes: Dict[str, Quote]) -> None:
        for lg in self.s.legs:  # wings first (they are listed first)
            self._fill(lg, quotes[lg.token], "BUY" if lg.side > 0 else "SELL", spot, vix, now, True)
            if lg.side < 0:
                lg.stop = round(lg.entry * (1.0 + self.p.sl_pct / 100.0), 2)
        self.s.phase = "OPEN"
        credit = sum(lg.entry for lg in self.s.legs if lg.side < 0)
        self.ledger.event("entered", credit=round(credit, 2),
                          stops={lg.symbol: lg.stop for lg in self.s.legs if lg.side < 0})

    def _close_all(self, quotes, spot, vix, now, why: str) -> None:
        for lg in self.s.legs:
            if lg.open:
                q = quotes.get(lg.token)
                if q is None:
                    continue  # retry next poll
                self._fill(lg, q, "BUY" if lg.side < 0 else "SELL", spot, vix, now, False, why)
        if any(lg.open for lg in self.s.legs):
            self._persist()
            return
        self._finish(why, spot, vix, now)

    def _mtm_exit(self, mtm: float, quotes, spot, vix, now) -> bool:
        """Max loss / profit lock / target on position MTM. Lock peak persists across restarts."""
        from research.timed_straddle.profit_lock import ProfitLockTracker, mtm_exit_reason

        peak = self.s.extra.get("lock_peak")
        tracker = ProfitLockTracker(self.p.profit_lock, float("-inf") if peak is None else float(peak))
        why = mtm_exit_reason(self.p, mtm, tracker)
        if tracker.rule is not None and tracker.peak != float("-inf"):
            before = self.s.extra.get("locked")
            self.s.extra["lock_peak"], self.s.extra["locked"] = tracker.peak, tracker.locked
            if tracker.locked is not None and tracker.locked != before:
                self.ledger.event("profit_lock", mtm=round(mtm, 2), locked=tracker.locked)
        if why:
            self._close_all(quotes, spot, vix, now, why)
            return True
        return False

    def force_close(self, quotes: Dict[str, Quote], now: datetime, why: str = "manual_stop") -> None:
        """Operator stop (Ctrl+C) — square off open legs at current quotes."""
        if self.s.phase != "OPEN":
            return
        spot_q = quotes.get(INDEX_TOKENS[self.p.symbol])
        vix_q = quotes.get(INDEX_TOKENS["INDIAVIX"])
        self._close_all(quotes, spot_q.ltp if spot_q else 0.0, vix_q.ltp if vix_q else None, now, why)

    def _finish(self, why: str, spot, vix, now) -> None:
        if any(lg.exit_reason == "sl" for lg in self.s.legs) and why == "time":
            why = "time_after_sl"
        self.s.phase, self.s.exit_reason = "DONE", why
        gross = sum((lg.exit - lg.entry) * lg.side for lg in self.s.legs)
        charges = sum(lg.charges for lg in self.s.legs)
        shorts = [lg for lg in self.s.legs if lg.side < 0]
        credit = sum(lg.entry for lg in shorts)
        model_credit = (sum(lg.model_entry for lg in shorts)
                        if all(lg.model_entry is not None for lg in shorts) else None)
        row = {
            "symbol": self.p.symbol, "expiry": self.s.expiry, "atm": self.s.atm,
            "entry_credit": round(credit, 2), "exit_reason": why,
            "gross_points": round(gross, 2), "charges": round(charges, 2),
            "net_pnl": round(gross * self.p.qty - charges, 2),
            "model_entry_credit": round(model_credit, 2) if model_credit is not None else "",
            "fill_vs_model_points": round(credit - model_credit, 2) if model_credit is not None else "",
            "legs": ";".join(f"{lg.symbol}:{lg.entry}->{lg.exit}({lg.exit_reason})" for lg in self.s.legs),
        }
        self.ledger.event("day_done", **row)
        self.ledger.write_summary(row)
        self._persist()
