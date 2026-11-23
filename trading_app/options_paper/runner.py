#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Options paper runner (OPT-PAPER). Live Angel quotes -> simulated fills -> logs/options_paper/.
Never places broker orders.

Start before the first entry time on a trading day; it exits when every strategy is DONE/SKIPPED:
  python -m trading_app.options_paper.runner --config config/options_paper.json   # all configured strategies
  python -m trading_app.options_paper.runner --symbol NIFTY                         # one timed straddle
  python -m trading_app.options_paper.runner --check     # login + quote smoke test, then exit

Ctrl+C squares off any open paper legs at the current quotes.
"""

from __future__ import annotations

import argparse
import json
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
from research.timed_straddle.profit_lock import ProfitLockRule
from research.timed_straddle.strangle import PremiumStrangleParams
from trading_app.options_paper.premium_strangle import PremiumStranglePaper
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


STRATEGY_TYPES = {"timed_straddle": (TimedStraddleParams, TimedStraddlePaper),
                  "premium_strangle": (PremiumStrangleParams, PremiumStranglePaper)}


def spec_to_params(spec: dict):
    """Config dict -> (name, params, paper class). Keys mirror the backtest runner flags."""
    kind = spec.get("type", "timed_straddle")
    if kind not in STRATEGY_TYPES:
        raise ValueError(f"Unknown strategy type {kind!r}; choose from {sorted(STRATEGY_TYPES)}")
    pcls, scls = STRATEGY_TYPES[kind]
    symbol = spec.get("symbol", "NIFTY")
    kw = dict(symbol=symbol, entry_hm=_hm(spec.get("entry", "09:20")), exit_hm=_hm(spec.get("exit", "15:15")),
              trail_sl_to_cost=spec.get("trail_sl_to_cost", True), target_rupees=spec.get("target"),
              max_loss_rupees=spec.get("max_loss"), lots=int(spec.get("lots", 1)),
              profit_lock=ProfitLockRule.parse(spec.get("profit_lock")))
    if kind == "timed_straddle":
        kw.update(sl_pct=float(spec.get("sl_pct", 25.0)), points_from_atm=float(spec.get("points", 0.0)),
                  buy_wings=spec.get("wings") is not None, wing_points=float(spec.get("wings") or 500.0),
                  max_dte=None if spec.get("max_dte") is None else int(spec["max_dte"]))
    else:
        tp = float(spec.get("target_premium", 40.0))
        kw.update(sl_pct=float(spec.get("sl_pct", 40.0)), target_premium=tp,
                  min_premium=float(spec.get("min_premium", 0.5 * tp)),
                  max_premium=float(spec.get("max_premium", 1.5 * tp)),
                  leg_target_pct=spec.get("leg_target_pct"), hedge_premium=spec.get("hedge_premium"),
                  max_adjustments=0,
                  max_dte=0 if spec.get("expiry_day_only") else (None if spec.get("max_dte") is None else int(spec["max_dte"])))
    name = spec.get("name") or f"{kind}_{symbol.lower()}"
    return name, pcls(**kw), scls


def _at(today: date, hm, extra_min: int = 0) -> datetime:
    return datetime.combine(today, datetime.min.time()) + timedelta(hours=hm[0], minutes=hm[1] + extra_min)


def _square_off_all(strategies, quotes_src, last_quotes, clock, why: str) -> None:
    for s in strategies:
        try:
            a, b = s.required_tokens()
            q = quotes_src.fetch(a, b) or last_quotes
        except Exception:
            q = last_quotes
        s.force_close(q, clock(), why)


def build_strategies(specs, chain, today: date, pricer=None, log_dir=None):
    """Instantiate paper strategies for today's enabled specs (each with its own ledger)."""
    strategies = []
    for spec in specs:
        name, params, scls = spec_to_params(spec)
        if chain.nearest_expiry(params.symbol, today) is None:
            log.warning("%s: no current %s expiries in scrip master — skipped", name, params.symbol)
            continue
        ledger = PaperLedger(name, today) if log_dir is None else PaperLedger(name, today, log_dir)
        strat = scls(params, chain, ledger, today, pricer, name=name)
        ledger.event("start", params=params.to_dict(), mode="PAPER_NO_ORDERS")
        strategies.append(strat)
        log.info("Loaded %s (%s). Ledger: %s", name, spec.get("type", "timed_straddle"), ledger.events_path)
    return strategies


def run_strategies(strategies, quotes_src, today: date, poll: float, clock=datetime.now, sleep=time.sleep,
                   should_stop=None, on_cycle=None) -> None:
    """
    One quote poll per cycle for the union of all strategies' tokens.
    ``should_stop()`` True -> square off open legs and return (dashboard Stop button).
    ``on_cycle(quotes)`` runs after every cycle (lock heartbeat, dashboard status cache).
    """
    first_entry = min(_at(today, s.p.entry_hm) for s in strategies)
    last_exit = max(_at(today, s.p.exit_hm, 10) for s in strategies)
    last_quotes = {}
    try:
        while not all(s.done for s in strategies):
            if should_stop is not None and should_stop():
                log.warning("Stop requested — squaring off open paper legs.")
                _square_off_all(strategies, quotes_src, last_quotes, clock, "manual_stop")
                break
            if on_cycle is not None:
                on_cycle(last_quotes)
            now = clock()
            if now > last_exit:
                log.warning("Past the last exit window; stopping.")
                break
            if now < first_entry - timedelta(seconds=30):
                sleep(min(30.0, (first_entry - now).total_seconds()))
                continue
            nse, nfo = [], []
            for s in strategies:
                if not s.done:
                    a, b = s.required_tokens()
                    nse += a
                    nfo += b
            try:
                quotes = quotes_src.fetch(nse, nfo)
            except Exception as exc:  # rate limit / network: keep going
                log.warning("Quote fetch failed: %s", exc)
                sleep(poll)
                continue
            index_quotes = [q for t, q in quotes.items() if t in INDEX_TOKENS.values() and q.feed_time]
            if index_quotes and all(q.feed_time.date() != today for q in index_quotes):
                log.warning("Exchange feed time %s is not today — market closed/holiday; not trading.",
                            index_quotes[0].feed_time)
                for s in strategies:
                    s.ledger.event("skipped", reason="stale_feed_market_closed", feed_time=str(index_quotes[0].feed_time))
                break
            last_quotes = quotes
            for s in strategies:
                before = s.s.phase
                try:
                    s.on_tick(now, quotes)
                except Exception as exc:  # one strategy must not take down the others
                    log.exception("%s tick failed: %s", s.name, exc)
                    s.ledger.event("error", error=str(exc))
                if s.s.phase != before:
                    log.info("%s: %s -> %s", s.name, before, s.s.phase)
            sleep(poll)
    except KeyboardInterrupt:
        log.warning("Ctrl+C — squaring off open paper legs.")
        _square_off_all(strategies, quotes_src, last_quotes, clock, "manual_stop")
    if on_cycle is not None:
        on_cycle(last_quotes)
    for s in strategies:
        log.info("DONE %s phase=%s reason=%s", s.name, s.s.phase, s.s.exit_reason)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Options paper runner (no broker orders)")
    ap.add_argument("--config", default=None, help="JSON file with poll_seconds + strategies list")
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

    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        specs = [s for s in cfg.get("strategies", []) if s.get("enabled", True)]
        poll = float(cfg.get("poll_seconds", args.poll))
    else:
        specs = [{"type": "timed_straddle", "symbol": args.symbol, "entry": args.entry, "exit": args.exit,
                  "points": args.points, "wings": args.wings, "sl_pct": args.sl_pct,
                  "trail_sl_to_cost": not args.no_trail, "target": args.target, "max_loss": args.max_loss,
                  "lots": args.lots, "name": f"timed_straddle_{args.symbol.lower()}"}]
        poll = args.poll
    if not specs:
        log.info("No enabled strategies.")
        return 0

    today = date.today()
    if today.weekday() >= 5:
        log.info("Weekend — nothing to do.")
        return 0

    from trading_app.options_paper.lock import LaneLock

    lock = LaneLock("scheduled_or_cli")
    if not lock.acquire():
        log.warning("Options paper lane is already running (%s) — not starting a second copy.", lock.current())
        return 0
    try:
        cm, chain = connect()
        strategies = build_strategies(specs, chain, today, build_model_pricer())
        if not strategies:
            return 1
        log.info("PAPER ONLY — no orders. %d strategies, poll %.0fs.", len(strategies), poll)
        run_strategies(strategies, AngelQuoteSource(cm.smart_api), today, poll, on_cycle=lambda q: lock.heartbeat())
        log.info("Summary: %s", strategies[0].ledger.summary_path)
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
