"""Real-price (1-minute option bars) replay engine — hand-built days, exact fills."""

from datetime import date

import numpy as np
import pytest

from research.real_options.engine import RealPriceEngine
from research.real_options.store import N_MIN, DayData, minute_index
from research.timed_straddle.params import TimedStraddleParams
from research.timed_straddle.strangle import PremiumStrangleParams

import pandas as pd


def _flat(px):
    a = np.zeros((N_MIN, 4), dtype=np.float32)
    a[:] = px
    return a


def _day(contracts, spot=24000.0, day=date(2024, 1, 9), expiry=date(2024, 1, 11)):
    """contracts: {(strike, 'CE'|'PE'): ohlc array [375,4]}"""
    keys = sorted(contracts)
    return DayData(day, expiry, _flat(spot), np.array([k for k, _ in keys], float),
                   np.array([0 if t == "CE" else 1 for _, t in keys], np.uint8),
                   np.stack([contracts[k] for k in keys]).astype(np.float32))


def _sp(**kw):
    base = dict(symbol="NIFTY", entry_hm=(9, 20), exit_hm=(15, 15), sl_pct=25.0, slippage_points=0.0,
                brokerage_per_order=0.0, lot_size=1, trail_sl_to_cost=True)
    base.update(kw)
    return TimedStraddleParams(**base)


def test_minute_index_tolerates_formats():
    got = minute_index(pd.Series(["09:15:00", "9:16", "2023-06-06 15:29:00", "  ", None]))
    assert list(got) == [0, 1, 374, -1, -1]


def test_straddle_entry_at_open_and_time_exit():
    ce, pe = _flat(100.0), _flat(100.0)
    ce[5:, :] = 80.0  # decays after entry
    pe[5:, :] = 90.0
    r = RealPriceEngine(_sp()).run([_day({(24000.0, "CE"): ce, (24000.0, "PE"): pe})]).iloc[0]
    assert r["exit_reason"] == "time"
    assert r["entry_premium"] == pytest.approx(80.0 + 90.0)  # 09:20 is minute 5 -> open = 80 / 90
    assert r["gross_points"] == pytest.approx(0.0)


def test_stop_uses_real_bar_high_and_pays_gap():
    ce, pe = _flat(100.0), _flat(100.0)
    ce[30] = [140.0, 150.0, 139.0, 145.0]   # gaps above the 125 stop at the bar open
    ce[31:] = 145.0
    pe[31:] = 60.0
    r = RealPriceEngine(_sp()).run([_day({(24000.0, "CE"): ce, (24000.0, "PE"): pe})]).iloc[0]
    legs = {lg["opt"]: lg for lg in r["legs"]}
    assert legs["CE"]["why"] == "sl" and legs["CE"]["exit"] == pytest.approx(140.0)  # max(stop 125, open 140)
    assert legs["PE"]["why"] in ("time", "sl")


def test_premium_strangle_picks_by_real_price_and_hedges_beyond():
    c = {}
    for k in range(23500, 24550, 50):
        dist = abs(k - 24000) / 50
        c[(float(k), "CE")] = _flat(max(120 - 15 * dist, 0.5) if k >= 24000 else 120 + 15 * dist)
        c[(float(k), "PE")] = _flat(max(120 - 15 * dist, 0.5) if k <= 24000 else 120 + 15 * dist)
    p = PremiumStrangleParams(symbol="NIFTY", entry_hm=(10, 0), exit_hm=(15, 0), slippage_points=0.0,
                              brokerage_per_order=0.0, lot_size=1, target_premium=45.0, min_premium=20.0,
                              max_premium=70.0, max_adjustments=0, hedge_premium=1.0, trail_sl_to_cost=False)
    legs = RealPriceEngine(p).run([_day(c)]).iloc[0]["legs"]
    shorts = {lg["opt"]: lg for lg in legs if lg["side"] < 0}
    hedges = {lg["opt"]: lg for lg in legs if lg["side"] > 0}
    assert shorts["CE"]["strike"] == 24250.0 and shorts["PE"]["strike"] == 23750.0   # 120-75 = 45
    assert hedges["CE"]["strike"] > 24250.0 and hedges["PE"]["strike"] < 23750.0


def test_expiry_only_filter_uses_store_expiry():
    ce, pe = _flat(100.0), _flat(100.0)
    p = PremiumStrangleParams(symbol="NIFTY", max_dte=0, target_premium=100.0, min_premium=50, max_premium=150,
                              slippage_points=0.0, brokerage_per_order=0.0, lot_size=1, max_adjustments=0)
    non_expiry = _day({(24000.0, "CE"): ce, (24000.0, "PE"): pe})
    expiry = _day({(24000.0, "CE"): ce, (24000.0, "PE"): pe}, day=date(2024, 1, 11))
    res = RealPriceEngine(p).run([non_expiry, expiry])
    assert list(res["dte"]) == [0]
