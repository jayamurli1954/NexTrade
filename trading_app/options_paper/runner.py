#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Options paper runner (OPT-PAPER). Live Angel quotes -> simulated fills -> logs/options_paper/.
Never places broker orders.

Start before 09:20 on a trading day and leave it running until it prints DONE:
  python -m trading_app.options_paper.runner --symbol NIFTY
  python -m trading_app.options_paper.runner --symbol NIFTY --sl-pct 30 --wings 500
  python -m trading_app.options_paper.runner --check     # login + quote smoke test, then exit

Ctrl+C squares off any open paper legs at the current quotes.
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.timed_straddle.params import TimedStraddleParams
from trading_app.options_paper.instruments import INDEX_TOKENS, OptionChainIndex
from trading_app.options_paper.ledger import PaperLedger
from trading_app.options_paper.quotes import AngelQuoteSource
from trading_app.options_paper.straddle import TimedStraddlePaper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("options_paper")


def _hm(s: str):
    h, m = s.split(":")
    return int(h), int(m)


def build_model_pricer():
    """Backtest pricing (BS + calibrated IV/VIX ratio) so every paper fill can be compared to the model."""
    from research.timed_straddle import pricing

    cal_path = ROOT / "research" / "data" / "timed_straddle" / f"iv_calibration_nifty_tb{pricing.TIME_BLEND:.2f}.pkl"
    if not cal_path.exists():
        log.warning("No IV calibration at %s — fills will not be compared to the model", cal_path)
        return None
    cal = pickle.loads(cal_path.read_bytes())

    def price(opt, strike, spot, vix, now, expiry):
        import pandas as pd

        ts, exp = pd.Timestamp(now), pd.Timestamp(expiry)
        iv = cal.iv(vix, opt, ts, exp, spot, strike)
        return pricing.bs_price(spot, strike, pricing.years_to_expiry(ts, exp), iv, 0.065, opt)

    return price


def connect():
    from ui_new.connection_manager import get_connection_manager

    cm = get_connection_manager()
    if not cm.connect_broker():
        raise SystemExit(f"Angel login failed: {getattr(cm, 'last_connection_error', None)}")
    cm.ensure_tokens_loaded()
    chain = OptionChainIndex.from_token_map(cm.token_map)
    return cm, chain


def check(symbol: str) -> int:
    cm, chain = connect()
    today = date.today()
    exp = chain.nearest_expiry(symbol, today)
    log.info("Option contracts in scrip master: %s; nearest %s expiry: %s", len(chain), symbol, exp)
    qs = AngelQuoteSource(cm.smart_api)
    q = qs.fetch([INDEX_TOKENS[symbol], INDEX_TOKENS["INDIAVIX"]], [])
    spot = q.get(INDEX_TOKENS[symbol])
    log.info("Spot %s, VIX %s", spot, q.get(INDEX_TOKENS["INDIAVIX"]))
    if spot and exp:
        p = TimedStraddleParams(symbol=symbol)
        atm = round(spot.ltp / p.strike_step) * p.strike_step
        legs = [chain.get(symbol, exp, atm, o) for o in ("CE", "PE")]
        lq = qs.fetch([], [c.token for c in legs if c])
        for c in legs:
            log.info("%s -> %s", c.symbol if c else None, lq.get(c.token) if c else None)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Options paper runner (no broker orders)")
    ap.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    ap.add_argument("--entry", default="09:20")
    ap.add_argument("--exit", default="15:15")
    ap.add_argument("--points", type=float, default=0.0)
    ap.add_argument("--wings", type=float, default=None)
    ap.add_argument("--sl-pct", type=float, default=25.0)
    ap.add_argument("--no-trail", action="store_true")
    ap.add_argument("--target", type=float, default=None)
    ap.add_argument("--max-loss", type=float, default=None)
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--poll", type=float, default=5.0, help="Seconds between quote polls")
    ap.add_argument("--check", action="store_true", help="Login + quote smoke test, then exit")
    args = ap.parse_args(argv)

    if args.check:
        return check(args.symbol)

    params = TimedStraddleParams(
        symbol=args.symbol, entry_hm=_hm(args.entry), exit_hm=_hm(args.exit), points_from_atm=args.points,
        buy_wings=args.wings is not None, wing_points=args.wings or 500.0, sl_pct=args.sl_pct,
        trail_sl_to_cost=not args.no_trail, target_rupees=args.target, max_loss_rupees=args.max_loss,
        lots=args.lots,
    )
    today = date.today()
    if today.weekday() >= 5:
        log.info("Weekend — nothing to do.")
        return 0

    cm, chain = connect()
    if chain.nearest_expiry(args.symbol, today) is None:
        raise SystemExit("No current option expiries in the scrip master — token cache may be stale.")
    ledger = PaperLedger(f"timed_straddle_{args.symbol.lower()}", today)
    strat = TimedStraddlePaper(params, chain, ledger, today, build_model_pricer())
    quotes_src = AngelQuoteSource(cm.smart_api)
    ledger.event("start", params=params.to_dict(), mode="PAPER_NO_ORDERS")
    log.info("PAPER ONLY — no orders. Ledger: %s", ledger.events_path)

    exit_dt = datetime.combine(today, datetime.min.time()) + timedelta(hours=params.exit_hm[0], minutes=params.exit_hm[1] + 10)
    entry_dt = datetime.combine(today, datetime.min.time()) + timedelta(hours=params.entry_hm[0], minutes=params.entry_hm[1])
    last_quotes = {}
    stale_warned = False
    try:
        while not strat.done:
            now = datetime.now()
            if now > exit_dt:
                log.warning("Past exit window; stopping.")
                break
            if now < entry_dt - timedelta(seconds=30) and strat.s.phase == "WAIT_ENTRY":
                time.sleep(min(30.0, (entry_dt - now).total_seconds()))
                continue
            nse, nfo = strat.required_tokens()
            try:
                quotes = quotes_src.fetch(nse, nfo)
            except Exception as exc:  # rate limit / network: keep going
                log.warning("Quote fetch failed: %s", exc)
                time.sleep(args.poll)
                continue
            spot_q = quotes.get(INDEX_TOKENS[args.symbol])
            if spot_q and spot_q.feed_time and spot_q.feed_time.date() != today:
                if not stale_warned:
                    log.warning("Exchange feed time %s is not today — market closed/holiday; not trading.", spot_q.feed_time)
                    ledger.event("skipped", reason="stale_feed_market_closed", feed_time=str(spot_q.feed_time))
                    stale_warned = True
                break
            last_quotes = quotes
            before = strat.s.phase
            strat.on_tick(now, quotes)
            if strat.s.phase != before:
                log.info("Phase %s -> %s", before, strat.s.phase)
            time.sleep(args.poll)
    except KeyboardInterrupt:
        log.warning("Ctrl+C — squaring off open paper legs.")
        try:
            nse, nfo = strat.required_tokens()
            last_quotes = quotes_src.fetch(nse, nfo) or last_quotes
        except Exception:
            pass
        strat.force_close(last_quotes, datetime.now(), "manual_stop")
    log.info("DONE phase=%s reason=%s. Summary: %s", strat.s.phase, strat.s.exit_reason, ledger.summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
