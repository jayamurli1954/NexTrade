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
