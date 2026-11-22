"""Tests for the timed short straddle research backtest (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from research.timed_straddle.costs import fill_cost
from research.timed_straddle.data import build_expiry_calendar
from research.timed_straddle.engine import TimedStraddleEngine
from research.timed_straddle.params import TimedStraddleParams
from research.timed_straddle.pricing import bs_price, implied_vol_vec


def _day(date: str, path, vix=15.0) -> pd.DataFrame:
    """5m bars 09:15..15:25 following ``path`` (list of closes, interpolated to 75 bars)."""
    idx = pd.date_range(f"{date} 09:15", f"{date} 15:25", freq="5min")
    closes = np.interp(np.linspace(0, len(path) - 1, len(idx)), np.arange(len(path)), path)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) + 2, "low": np.minimum(opens, closes) - 2,
                         "close": closes, "vix": vix}, index=idx)


def _params(**kw):
    base = dict(symbol="NIFTY", entry_hm=(9, 20), exit_hm=(15, 15), sl_pct=25.0, slippage_points=0.0,
                brokerage_per_order=0.0, lot_size=1)
    base.update(kw)
    return TimedStraddleParams(**base)


def test_put_call_parity_and_iv_roundtrip():
    s, k, t, r, iv = 24000.0, 24000.0, 3 / 365, 0.065, 0.14
    ce, pe = bs_price(s, k, t, iv, r, "CE"), bs_price(s, k, t, iv, r, "PE")
    assert ce - pe == pytest.approx(s - k * np.exp(-r * t), abs=0.05)
    got = implied_vol_vec(np.array([ce]), s, k, t, r, np.array([True]))[0]
    assert got == pytest.approx(iv, abs=1e-4)


def test_sell_fill_pays_stt_buy_pays_stamp():
    sell, buy = fill_cost(100.0, 65, "SELL", 0.0), fill_cost(100.0, 65, "BUY", 0.0)
    assert sell > buy > 0


def test_expiry_calendar_holiday_shifts_to_previous_day():
    days = pd.bdate_range("2019-03-04", "2019-03-15")
    days = days[days != pd.Timestamp("2019-03-07")]  # Thursday holiday
    cal = build_expiry_calendar("NIFTY", days)
    assert cal[pd.Timestamp("2019-03-05")] == pd.Timestamp("2019-03-06")
    assert cal[pd.Timestamp("2019-03-11")] == pd.Timestamp("2019-03-14")


def test_banknifty_has_no_weeklies_after_discontinuation():
    days = pd.bdate_range("2024-11-25", "2024-12-06")
    assert build_expiry_calendar("BANKNIFTY", days) == {}


def test_flat_day_keeps_theta_and_exits_on_time():
    panel = _day("2024-01-09", [21500, 21500])
    expiry = {pd.Timestamp("2024-01-09"): pd.Timestamp("2024-01-11")}
    res = TimedStraddleEngine(_params()).run(panel, expiry)
    assert len(res) == 1
    row = res.iloc[0]
    assert row["exit_reason"] == "time"
    assert row["gross_points"] > 0  # premium decays on a flat day


def test_trend_day_hits_ce_stop_and_trails_pe_to_cost():
    panel = _day("2024-01-09", [21500, 21900, 21900])
    expiry = {pd.Timestamp("2024-01-09"): pd.Timestamp("2024-01-11")}
    res = TimedStraddleEngine(_params(trail_sl_to_cost=True)).run(panel, expiry)
    legs = {lg["opt"]: lg for lg in res.iloc[0]["legs"]}
    assert legs["CE"]["why"] == "sl"
    # CE stop filled at or above entry * 1.25
    assert legs["CE"]["exit"] >= legs["CE"]["entry"] * 1.25 - 0.01
    # PE survives (market went up) and is closed at time, profitable
    assert legs["PE"]["why"] == "time"
    assert legs["PE"]["exit"] < legs["PE"]["entry"]


def test_max_loss_exits_position():
    panel = _day("2024-01-09", [21500, 22300])
    expiry = {pd.Timestamp("2024-01-09"): pd.Timestamp("2024-01-11")}
    res = TimedStraddleEngine(_params(sl_pct=500.0, max_loss_rupees=50.0)).run(panel, expiry)
    assert res.iloc[0]["exit_reason"] == "max_loss"


def test_wings_cap_loss_vs_naked():
    panel = _day("2024-01-09", [21500, 22500])
    expiry = {pd.Timestamp("2024-01-09"): pd.Timestamp("2024-01-11")}
    naked = TimedStraddleEngine(_params(sl_pct=1000.0)).run(panel, expiry).iloc[0]
    hedged = TimedStraddleEngine(_params(sl_pct=1000.0, buy_wings=True, wing_points=200)).run(panel, expiry).iloc[0]
    assert hedged["gross_points"] > naked["gross_points"]
