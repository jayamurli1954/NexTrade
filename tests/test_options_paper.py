"""Tests for the options paper lane (fake quotes; no network, no broker)."""

import csv
from datetime import date, datetime

import pytest

from research.timed_straddle.params import TimedStraddleParams
from trading_app.options_paper.instruments import INDEX_TOKENS, OptionChainIndex
from trading_app.options_paper.ledger import PaperLedger
from trading_app.options_paper.quotes import AngelQuoteSource, Quote, parse_market_data
from trading_app.options_paper.straddle import TimedStraddlePaper

DAY = date(2026, 11, 24)
EXP = "24NOV26"
TOKEN_MAP = {
    f"NFO:NIFTY{EXP}24000CE": "1001", f"NFO:NIFTY{EXP}24000PE": "1002",
    f"NFO:NIFTY{EXP}24500CE": "1003", f"NFO:NIFTY{EXP}23500PE": "1004",
    "NFO:NIFTY01DEC2624000CE": "2001", "NSE:NIFTY": "99926000", "NFO:NIFTYNXT5024NOV2624000CE": "9",
}
SPOT, VIX = INDEX_TOKENS["NIFTY"], INDEX_TOKENS["INDIAVIX"]


def q(tok, px, spread=0.5):
    return Quote(tok, px, px - spread / 2, px + spread / 2)


def ticks(spot, ce, pe, wings=None):
    out = {SPOT: Quote(SPOT, spot), VIX: Quote(VIX, 14.0), "1001": q("1001", ce), "1002": q("1002", pe)}
    if wings:
        out["1003"], out["1004"] = q("1003", wings[0]), q("1004", wings[1])
    return out


@pytest.fixture
def chain():
    return OptionChainIndex.from_token_map(TOKEN_MAP)


def _strategy(tmp_path, chain, **kw):
    p = TimedStraddleParams(symbol="NIFTY", sl_pct=25.0, lot_size=65, **kw)
    return TimedStraddlePaper(p, chain, PaperLedger("t", DAY, tmp_path), DAY), tmp_path


def test_chain_parses_only_index_options(chain):
    assert len(chain) == 5
    assert chain.nearest_expiry("NIFTY", DAY) == date(2026, 11, 24)
    assert chain.nearest_expiry("NIFTY", date(2026, 11, 25)) == date(2026, 12, 1)
    assert chain.get("NIFTY", DAY, 24000, "CE").token == "1001"


def test_parse_market_data_best_bid_ask():
    resp = {"status": True, "data": {"fetched": [{"symbolToken": "1001", "ltp": 100.0,
            "exchFeedTime": "24-Nov-2026 09:20:01",
            "depth": {"buy": [{"price": 99.5}], "sell": [{"price": 0}, {"price": 100.5}]}}]}}
    got = parse_market_data(resp)["1001"]
    assert (got.bid, got.ask, got.feed_time.day) == (99.5, 100.5, 24)
    with pytest.raises(RuntimeError):
        parse_market_data({"status": False, "message": "AB1004"})


def test_quote_source_uses_market_data_only():
    class Api:
        def __init__(self):
            self.calls = []

        def getMarketData(self, mode, req):
            self.calls.append((mode, req))
            return {"status": True, "data": {"fetched": []}}

        def placeOrder(self, *a, **k):  # must never be called
            raise AssertionError("paper lane must not place orders")

    api = Api()
    AngelQuoteSource(api, rest_call=lambda label, fn: fn()).fetch(["99926000"], ["1001"])
    assert api.calls == [("FULL", {"NSE": ["99926000"], "NFO": ["1001"]})]


def test_full_day_sl_trail_and_time_exit(tmp_path, chain):
    s, root = _strategy(tmp_path, chain)
    s.on_tick(datetime(2026, 11, 24, 9, 10), ticks(24010, 100, 100))
    assert s.s.phase == "WAIT_ENTRY"
    index_only = {k: v for k, v in ticks(24010, 100, 100).items() if k in (SPOT, VIX)}
    s.on_tick(datetime(2026, 11, 24, 9, 20), index_only)  # live loop only has index quotes here
    assert s.s.phase == "READY" and s.s.atm == 24000
    assert s.required_tokens()[1] == ["1001", "1002"]
    s.on_tick(datetime(2026, 11, 24, 9, 20, 5), ticks(24010, 100, 100))
    assert s.s.phase == "OPEN"
    ce, pe = s.s.legs
    assert ce.entry == 99.75 and ce.stop == round(99.75 * 1.25, 2)  # sold at bid
    s.on_tick(datetime(2026, 11, 24, 10, 0), ticks(24150, 126, 60))   # CE LTP through stop
    assert ce.exit == 126.25 and ce.exit_reason == "sl"               # bought at ask
    assert pe.stop == pe.entry                                         # trailed to cost
    s.on_tick(datetime(2026, 11, 24, 15, 15), ticks(24200, 150, 40))
    assert s.done and s.s.exit_reason == "time_after_sl"
    rows = list(csv.DictReader((root / "summary.csv").open()))
    assert rows[0]["exit_reason"] == "time_after_sl"
    expected_gross = (99.75 - 126.25) + (99.75 - 40.25)
    assert float(rows[0]["gross_points"]) == pytest.approx(expected_gross)
    assert float(rows[0]["net_pnl"]) < expected_gross * 65  # charges deducted


def test_trailed_leg_stops_at_cost(tmp_path, chain):
    s, _ = _strategy(tmp_path, chain)
    s.on_tick(datetime(2026, 11, 24, 9, 20), ticks(24000, 100, 100))
    s.on_tick(datetime(2026, 11, 24, 9, 21), ticks(24000, 100, 100))
    s.on_tick(datetime(2026, 11, 24, 10, 0), ticks(24150, 130, 60))
    s.on_tick(datetime(2026, 11, 24, 11, 0), ticks(24000, 90, 100))  # PE back to cost
    assert s.done and s.s.exit_reason == "all_sl"


def test_wings_entered_and_sold_on_stop(tmp_path, chain):
    s, _ = _strategy(tmp_path, chain, buy_wings=True, wing_points=500)
    s.on_tick(datetime(2026, 11, 24, 9, 20), ticks(24000, 100, 100, (20, 20)))
    s.on_tick(datetime(2026, 11, 24, 9, 21), ticks(24000, 100, 100, (20, 20)))
    wing_ce, wing_pe, ce, pe = s.s.legs
    assert wing_ce.side == 1 and wing_ce.entry == 20.25
    s.on_tick(datetime(2026, 11, 24, 10, 0), ticks(24200, 130, 50, (35, 10)))
    assert ce.exit_reason == "sl" and wing_ce.exit_reason == "sl_wing" and wing_pe.open


def test_restart_resumes_open_position(tmp_path, chain):
    s, _ = _strategy(tmp_path, chain)
    s.on_tick(datetime(2026, 11, 24, 9, 20), ticks(24000, 100, 100))
    s.on_tick(datetime(2026, 11, 24, 9, 21), ticks(24000, 100, 100))
    again, _ = _strategy(tmp_path, chain)
    assert again.s.phase == "OPEN" and [lg.entry for lg in again.s.legs] == [99.75, 99.75]


def test_missed_entry_window_skips_day(tmp_path, chain):
    s, _ = _strategy(tmp_path, chain)
    s.on_tick(datetime(2026, 11, 24, 10, 30), ticks(24000, 100, 100))
    assert s.s.phase == "SKIPPED"


def test_force_close_squares_off(tmp_path, chain):
    s, _ = _strategy(tmp_path, chain)
    s.on_tick(datetime(2026, 11, 24, 9, 20), ticks(24000, 100, 100))
    s.on_tick(datetime(2026, 11, 24, 9, 21), ticks(24000, 100, 100))
    s.force_close(ticks(24000, 95, 95), datetime(2026, 11, 24, 12, 0))
    assert s.done and s.s.exit_reason == "manual_stop"


# ---------------------------------------------------------------- premium strangle paper + multi-strategy runner
from research.timed_straddle.strangle import PremiumStrangleParams
from trading_app.options_paper.premium_strangle import PremiumStranglePaper
from trading_app.options_paper.runner import run_strategies, spec_to_params

EXPIRY_DAY = date(2026, 11, 24)  # matches EXP in TOKEN_MAP


def _chain_with_strikes():
    tm = {}
    tok = 5000
    for k in range(23000, 25050, 50):
        for o in ("CE", "PE"):
            tm[f"NFO:NIFTY{EXP}{k}{o}"] = str(tok)
            tok += 1
    return OptionChainIndex.from_token_map(tm), tm


def _premium(o, k, spot=24000.0):
    """Toy smile: premium falls 10/strike step away from ATM, floor 0.5."""
    dist = (k - spot) if o == "CE" else (spot - k)
    return max(120.0 - dist / 50.0 * 10.0, 0.5)


def _all_quotes(tm, spot=24000.0, bump=None):
    out = {SPOT: Quote(SPOT, spot), VIX: Quote(VIX, 14.0)}
    for key, tok in tm.items():
        k, o = float(key[len(f"NFO:NIFTY{EXP}"):-2]), key[-2:]
        px = _premium(o, k, spot) * (bump.get(o, 1.0) if bump else 1.0)
        out[tok] = Quote(tok, round(px, 2), round(px - 0.1, 2), round(px + 0.1, 2))
    return out


def _pstrat(tmp_path, chain, day=EXPIRY_DAY, **kw):
    base = dict(symbol="NIFTY", entry_hm=(10, 0), exit_hm=(15, 0), lot_size=65, target_premium=50.0,
                min_premium=25.0, max_premium=75.0, sl_pct=30.0, leg_target_pct=99.0, trail_sl_to_cost=False,
                hedge_premium=0.8, max_dte=0)
    base.update(kw)
    return PremiumStranglePaper(PremiumStrangleParams(**base), chain, PaperLedger("p", day, tmp_path), day)


def test_expiry_only_strategy_skips_non_expiry_day(tmp_path):
    chain, tm = _chain_with_strikes()
    s = _pstrat(tmp_path, chain, day=date(2026, 11, 20))
    s.on_tick(datetime(2026, 11, 20, 10, 0), _all_quotes(tm))
    assert s.s.phase == "SKIPPED" and s.s.exit_reason.startswith("not_trading_day")


def test_expiry_strangle_selects_by_premium_hedges_then_enters(tmp_path):
    chain, tm = _chain_with_strikes()
    s = _pstrat(tmp_path, chain)
    q = _all_quotes(tm)
    s.on_tick(datetime(2026, 11, 24, 10, 0), q)
    assert s.s.phase == "SELECT_SHORTS" and len(s.required_tokens()[1]) <= 48
    s.on_tick(datetime(2026, 11, 24, 10, 0, 5), q)
    assert s.s.phase == "SELECT_HEDGES"
    s.on_tick(datetime(2026, 11, 24, 10, 0, 10), q)
    assert s.s.phase == "READY"
    s.on_tick(datetime(2026, 11, 24, 10, 0, 15), q)
    assert s.s.phase == "OPEN"
    wce, wpe, ce, pe = s.s.legs
    assert (ce.strike, pe.strike) == (24350.0, 23650.0)          # toy premium 50 each
    assert wce.side == 1 and wce.strike > ce.strike and wpe.strike < pe.strike
    assert wce.entry <= 1.0                                        # ~0.8 hedge, bought at ask
    assert ce.stop == round(ce.entry * 1.30, 2)


def test_expiry_strangle_stop_closes_one_leg_and_keeps_hedges(tmp_path):
    chain, tm = _chain_with_strikes()
    s = _pstrat(tmp_path, chain)
    q = _all_quotes(tm)
    for sec in (0, 5, 10, 15):
        s.on_tick(datetime(2026, 11, 24, 10, 0, sec), q)
    s.on_tick(datetime(2026, 11, 24, 11, 0), _all_quotes(tm, bump={"CE": 1.5, "PE": 0.5}))
    wce, wpe, ce, pe = s.s.legs
    assert ce.exit_reason == "sl" and pe.open and wce.open and wpe.open
    s.on_tick(datetime(2026, 11, 24, 15, 0), _all_quotes(tm, bump={"CE": 1.5, "PE": 0.2}))
    assert s.done and s.s.exit_reason == "time_after_sl"


def test_expiry_strangle_leg_target_then_all_out_closes_hedges(tmp_path):
    chain, tm = _chain_with_strikes()
    s = _pstrat(tmp_path, chain, sl_pct=500.0)
    q = _all_quotes(tm)
    for sec in (0, 5, 10, 15):
        s.on_tick(datetime(2026, 11, 24, 10, 0, sec), q)
    s.on_tick(datetime(2026, 11, 24, 14, 0), _all_quotes(tm, bump={"CE": 0.005, "PE": 0.005}))
    assert s.done and s.s.exit_reason == "all_legs_out"
    assert all(not lg.open for lg in s.s.legs)


def test_spec_to_params_builds_both_types():
    n1, p1, c1 = spec_to_params({"type": "timed_straddle", "symbol": "NIFTY", "sl_pct": 30})
    n2, p2, c2 = spec_to_params({"type": "premium_strangle", "name": "exp", "expiry_day_only": True,
                                 "target_premium": 50, "hedge_premium": 0.8})
    assert c1 is TimedStraddlePaper and p1.sl_pct == 30
    assert c2 is PremiumStranglePaper and n2 == "exp" and p2.max_dte == 0 and p2.min_premium == 25


def test_run_strategies_drives_two_strategies_with_one_poll(tmp_path):
    chain, tm = _chain_with_strikes()
    a = _pstrat(tmp_path / "a", chain)
    b = _strategy(tmp_path / "b", chain)[0]  # timed straddle on the small TOKEN_MAP chain
    b.chain = OptionChainIndex.from_token_map({**TOKEN_MAP, **tm})
    times = iter([datetime(2026, 11, 24, 9, 20)] + [datetime(2026, 11, 24, 10, 0, s) for s in range(0, 60, 5)]
                 + [datetime(2026, 11, 24, 15, 15)] * 3)

    class Src:
        calls = 0

        def fetch(self, nse, nfo):
            Src.calls += 1
            q = _all_quotes(tm)
            q.update({"1001": q.get("1001", Quote("1001", 100, 99.75, 100.25)),
                      "1002": Quote("1002", 100, 99.75, 100.25)})
            return q

    run_strategies([a, b], Src(), EXPIRY_DAY, poll=0, clock=lambda: next(times), sleep=lambda s: None)
    assert a.done and b.done
    assert Src.calls <= 16


def test_quote_source_chunks_at_50_tokens():
    class Api:
        sizes = []

        def getMarketData(self, mode, req):
            Api.sizes.append(sum(len(v) for v in req.values()))
            return {"status": True, "data": {"fetched": []}}

    AngelQuoteSource(Api(), rest_call=lambda label, fn: fn()).fetch(["1", "2"], [str(i) for i in range(100, 160)])
    assert Api.sizes == [50, 12]


def test_paper_profit_lock_exits_and_persists_peak(tmp_path, chain):
    from research.timed_straddle.profit_lock import ProfitLockRule

    s, _ = _strategy(tmp_path, chain, profit_lock=ProfitLockRule(1000, 300, 0, 0))
    s.on_tick(datetime(2026, 11, 24, 9, 20), ticks(24000, 100, 100))
    s.on_tick(datetime(2026, 11, 24, 9, 21), ticks(24000, 100, 100))
    s.on_tick(datetime(2026, 11, 24, 11, 0), ticks(24000, 90, 90))     # +~1235 MTM -> lock 300 armed
    assert s.s.extra["locked"] == 300
    again, _ = _strategy(tmp_path, chain, profit_lock=ProfitLockRule(1000, 300, 0, 0))
    assert again.s.extra["lock_peak"] > 1000                              # survives restart
    again.on_tick(datetime(2026, 11, 24, 12, 0), ticks(24000, 97, 97))  # gives back to ~+240
    assert again.done and again.s.exit_reason == "profit_lock"


# ---------------------------------------------------------------- dashboard service + lock
import json as _json
import threading as _threading
import time as _time

from trading_app.options_paper.lock import LaneLock
from trading_app.options_paper.service import OptionsPaperService


def test_lane_lock_blocks_second_owner_and_expires(tmp_path):
    a = LaneLock("dashboard", path=tmp_path / "l.lock", stale_sec=60)
    b = LaneLock("scheduled", path=tmp_path / "l.lock", stale_sec=60)
    assert a.acquire() and not b.acquire()
    a.release()
    assert b.acquire()
    stale = LaneLock("x", path=tmp_path / "l.lock", stale_sec=0.0)   # heartbeat considered stale immediately
    assert stale.acquire()


def _svc(tmp_path, specs):
    cfg = tmp_path / "options_paper.json"
    cfg.write_text(_json.dumps({"poll_seconds": 0.01, "strategies": specs}))
    chain = OptionChainIndex.from_token_map(TOKEN_MAP)

    class Src:
        def __init__(self, api):
            pass

        def fetch(self, nse, nfo):
            return ticks(24000, 100, 100)

    return OptionsPaperService(config_path=cfg, log_dir=tmp_path / "logs",
                               connect=lambda: (object(), chain), quote_source_factory=Src)


def test_service_toggle_and_status(tmp_path):
    svc = _svc(tmp_path, [{"name": "a", "type": "timed_straddle", "enabled": False, "symbol": "NIFTY"}])
    svc.set_enabled("a", True)
    st = svc.status()
    assert st["config"][0]["enabled"] is True and st["running"] is False and st["mode"] == "PAPER_NO_ORDERS"
    with pytest.raises(KeyError):
        svc.set_enabled("missing", True)


def test_service_start_stop_squares_off_and_releases_lock(tmp_path, monkeypatch):
    import trading_app.options_paper.service as service_mod
    from datetime import date as _date

    class FakeDate(_date):
        @classmethod
        def today(cls):
            return DAY  # Tuesday 2026-11-24, an expiry in TOKEN_MAP

    monkeypatch.setattr(service_mod, "date", FakeDate)
    import trading_app.options_paper.runner as runner_mod
    monkeypatch.setattr(runner_mod, "build_model_pricer", lambda: None)
    # entry window open "now": strategy enters immediately
    spec = {"name": "a", "type": "timed_straddle", "enabled": True, "symbol": "NIFTY", "entry": "09:59", "exit": "23:58"}
    svc = _svc(tmp_path, [spec])
    orig_run = runner_mod.run_strategies

    def run_with_clock(strategies, qs, today, poll, **kw):
        kw["clock"] = lambda: datetime(2026, 11, 24, 10, 0)
        return orig_run(strategies, qs, today, poll, **kw)

    monkeypatch.setattr(runner_mod, "run_strategies", run_with_clock)
    assert svc.start()["success"]
    other = LaneLock("scheduled", path=tmp_path / "logs" / "runner.lock")
    assert not other.acquire()                         # dashboard owns the lane
    for _ in range(200):
        if svc.status()["strategies"] and svc.status()["strategies"][0]["phase"] == "OPEN":
            break
        _time.sleep(0.02)
    assert svc.status()["strategies"][0]["phase"] == "OPEN"
    assert svc.stop()["success"]
    for _ in range(200):
        if not svc.running:
            break
        _time.sleep(0.02)
    assert not svc.running
    assert svc.status()["strategies"][0]["reason"] == "manual_stop"
    assert other.acquire()                             # lock released


def test_auto_start_rules(tmp_path):
    svc = _svc(tmp_path, [{"name": "a", "type": "timed_straddle", "enabled": True, "symbol": "NIFTY"}])
    calls = []
    svc.start = lambda: (calls.append(1), setattr(svc, "_started_day", date(2026, 11, 24)), {"success": True, "message": "ok"})[-1]
    svc.set_auto_start(False)
    assert svc.auto_start_tick(datetime(2026, 11, 24, 9, 5)) is None          # off
    svc.set_auto_start(True)
    assert svc.auto_start_tick(datetime(2026, 11, 22, 9, 5)) is None          # Sunday
    assert svc.auto_start_tick(datetime(2026, 11, 24, 8, 59)) is None         # before 09:00
    assert svc.auto_start_tick(datetime(2026, 11, 24, 14, 31)) is None        # after window
    assert svc.auto_start_tick(datetime(2026, 11, 24, 9, 5))["success"]       # fires
    assert svc.auto_start_tick(datetime(2026, 11, 24, 9, 30)) is None         # once per day (also after Stop)
    assert len(calls) == 1
    held = LaneLock("scheduled", path=tmp_path / "logs" / "runner.lock")
    assert held.acquire()
    assert svc.auto_start_tick(datetime(2026, 11, 25, 9, 5)) is None          # another owner holds the lane
    held.release()
    assert svc.auto_start_tick(datetime(2026, 11, 25, 9, 5))["success"]       # next day, free -> fires
    assert svc.status()["auto_start"] is True


# ---------------------------------------------------------------- daily / cumulative report
def _write_summary(path, rows):
    import csv as _csv

    fields = ["date", "strategy", "symbol", "expiry", "atm", "entry_credit", "exit_reason", "gross_points",
              "charges", "net_pnl", "model_entry_credit", "fill_vs_model_points", "legs"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({**{f: "" for f in fields}, **r})


def test_report_daily_cumulative_drawdown_and_excel(tmp_path):
    from trading_app.options_paper.report import build_report, write_excel
    import openpyxl

    _write_summary(tmp_path / "summary.csv", [
        {"date": "2026-11-23", "strategy": "a", "net_pnl": 1000, "charges": 100, "legs": "X:10->5(time)"},
        {"date": "2026-11-23", "strategy": "b", "net_pnl": -400, "charges": 50},
        {"date": "2026-11-25", "strategy": "a", "net_pnl": -1500, "charges": 100},
        {"date": "2026-11-25", "strategy": "a", "net_pnl": -1200, "charges": 100},   # restarted day: last row wins
        {"date": "2026-11-26", "strategy": "b", "net_pnl": 300, "charges": 50},
    ])
    rep = build_report(tmp_path)
    assert rep["has_data"] and rep["strategies"] == ["a", "b"]
    assert [d["date"] for d in rep["daily"]] == ["2026-11-26", "2026-11-25", "2026-11-23"]   # newest first
    assert rep["daily"][0]["cumulative"] == pytest.approx(1000 - 400 - 1200 + 300)
    total = next(s for s in rep["stats"] if s["strategy"] == "ALL STRATEGIES")
    assert total["days"] == 3 and total["net_pnl"] == pytest.approx(-300)
    assert total["max_drawdown"] == pytest.approx(-1200)        # peak +600 after day 1 -> -600 after day 2
    a = next(s for s in rep["stats"] if s["strategy"] == "a")
    assert a["win_rate_pct"] == 50.0 and a["worst_day"] == -1200
    x = write_excel(tmp_path, out_dir=tmp_path / "out")
    wb = openpyxl.load_workbook(x)
    assert wb.sheetnames == ["Summary", "Daily & Cumulative", "Strategy-days", "Legs"]
    assert wb["Legs"].max_row == 2


def test_report_empty(tmp_path):
    from trading_app.options_paper.report import build_report, write_excel

    assert build_report(tmp_path)["has_data"] is False
    assert write_excel(tmp_path, out_dir=tmp_path) is None


# ---------------------------------------------------------------- BANKNIFTY monthly straddle (max_dte filter)
def _bn_chain():
    tm = {"NFO:BANKNIFTY29DEC2661000CE": "7001", "NFO:BANKNIFTY29DEC2661000PE": "7002",
          "NFO:BANKNIFTY29DEC2661100CE": "7003", "NFO:BANKNIFTY29DEC2661100PE": "7004"}
    return OptionChainIndex.from_token_map(tm)


def _bn_strategy(tmp_path, day):
    from trading_app.options_paper.runner import spec_to_params

    name, params, scls = spec_to_params({"name": "bn", "type": "timed_straddle", "symbol": "BANKNIFTY", "entry": "09:20",
                                         "exit": "15:05", "sl_pct": 35, "trail_sl_to_cost": False, "max_dte": 13})
    assert params.max_dte == 13 and params.qty == 30 and params.strike_step == 100
    return scls(params, _bn_chain(), PaperLedger(name, day, tmp_path), day, name=name)


def _bn_ticks(spot, ce, pe):
    bn = INDEX_TOKENS["BANKNIFTY"]
    return {bn: Quote(bn, spot), VIX: Quote(VIX, 14.0), "7001": q("7001", ce), "7002": q("7002", pe)}


def test_bn_monthly_straddle_skips_far_from_expiry(tmp_path):
    s = _bn_strategy(tmp_path, date(2026, 12, 1))            # 28 days to 29-Dec expiry
    s.on_tick(datetime(2026, 12, 1, 9, 20), _bn_ticks(61020, 900, 880))
    assert s.s.phase == "SKIPPED" and s.s.exit_reason == "not_trading_day_dte28"


def test_bn_monthly_straddle_trades_inside_window(tmp_path):
    s = _bn_strategy(tmp_path, date(2026, 12, 17))           # 12 days to expiry
    idx = {k: v for k, v in _bn_ticks(61020, 600, 580).items() if k in (INDEX_TOKENS["BANKNIFTY"], VIX)}
    s.on_tick(datetime(2026, 12, 17, 9, 20), idx)
    assert s.s.phase == "READY" and s.s.atm == 61000
    s.on_tick(datetime(2026, 12, 17, 9, 20, 5), _bn_ticks(61020, 600, 580))
    assert s.s.phase == "OPEN"
    ce, pe = s.s.legs
    assert ce.stop == round(ce.entry * 1.35, 2)
    s.on_tick(datetime(2026, 12, 17, 10, 0), _bn_ticks(61500, 850, 300))   # CE through stop, no trail
    assert ce.exit_reason == "sl" and pe.stop == round(pe.entry * 1.35, 2)
