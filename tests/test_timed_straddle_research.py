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


# ---------------------------------------------------------------- premium strangle
from research.timed_straddle.strangle import PremiumStrangleEngine, PremiumStrangleParams


def _sparams(**kw):
    base = dict(symbol="NIFTY", entry_hm=(9, 20), exit_hm=(15, 15), slippage_points=0.0,
                brokerage_per_order=0.0, lot_size=1, target_premium=40.0, min_premium=20.0, max_premium=60.0)
    base.update(kw)
    return PremiumStrangleParams(**base)


EXP = {pd.Timestamp("2024-01-09"): pd.Timestamp("2024-01-11")}


def test_pick_strike_hits_premium_band_on_otm_side():
    eng = PremiumStrangleEngine(_sparams())
    ts, exp = pd.Timestamp("2024-01-09 09:20"), pd.Timestamp("2024-01-11")
    ce = eng.pick_strike("CE", 21500.0, 15.0, ts, exp, 40.0)
    pe = eng.pick_strike("PE", 21500.0, 15.0, ts, exp, 40.0)
    assert ce[0] > 21500 and pe[0] < 21500
    assert 20.0 <= ce[1] <= 60.0 and 20.0 <= pe[1] <= 60.0


def test_strangle_flat_day_keeps_premium():
    res = PremiumStrangleEngine(_sparams()).run(_day("2024-01-09", [21500, 21500]), EXP)
    row = res.iloc[0]
    assert row["exit_reason"] == "time" and row["gross_points"] > 0
    assert len(row["legs"]) == 2


def test_strangle_stop_triggers_premium_matched_reentry():
    res = PremiumStrangleEngine(_sparams(sl_pct=40.0, max_adjustments=1)).run(
        _day("2024-01-09", [21500, 21800, 21800]), EXP)
    legs = res.iloc[0]["legs"]
    ces = [lg for lg in legs if lg["opt"] == "CE"]
    assert ces[0]["why"] == "sl"
    assert len(ces) == 2 and ces[1]["strike"] > ces[0]["strike"]  # re-sold further up
    assert res.iloc[0]["exit_reason"] in ("time_after_adjust", "all_legs_out")


def test_strangle_no_adjustments_when_disabled():
    res = PremiumStrangleEngine(_sparams(sl_pct=40.0, max_adjustments=0)).run(
        _day("2024-01-09", [21500, 21800, 21800]), EXP)
    assert len(res.iloc[0]["legs"]) == 2


def test_strangle_hedge_wings_reduce_trend_loss():
    path = [21500, 22600]
    naked = PremiumStrangleEngine(_sparams(sl_pct=5000.0, max_adjustments=0)).run(_day("2024-01-09", path), EXP).iloc[0]
    hedged = PremiumStrangleEngine(_sparams(sl_pct=5000.0, max_adjustments=0, hedge_points=500.0)).run(
        _day("2024-01-09", path), EXP).iloc[0]
    assert hedged["gross_points"] > naked["gross_points"]


def test_premium_hedge_sits_beyond_short_strikes():
    res = PremiumStrangleEngine(_sparams(max_adjustments=0, hedge_premium=1.0)).run(_day("2024-01-09", [21500, 21500]), EXP)
    legs = {(lg["opt"], lg["side"]): lg for lg in res.iloc[0]["legs"]}
    assert legs[("CE", 1)]["strike"] > legs[("CE", -1)]["strike"]
    assert legs[("PE", 1)]["strike"] < legs[("PE", -1)]["strike"]
    assert legs[("CE", 1)]["entry"] < 5.0


def test_pre_weekly_era_uses_monthly_expiry_only():
    days = pd.bdate_range("2018-03-01", "2018-03-29")
    cal = build_expiry_calendar("NIFTY", days)
    assert set(cal.values()) == {pd.Timestamp("2018-03-29")}
    assert pd.Timestamp("2018-03-05") not in cal  # >7 days before monthly expiry: not traded


# ---------------------------------------------------------------- profit lock
from research.timed_straddle.profit_lock import ProfitLockRule, ProfitLockTracker


def test_profit_lock_rule_steps_and_never_moves_down():
    r = ProfitLockRule(trigger=2000, lock=500, step=500, increment=250)
    assert r.locked_for(1999) is None
    assert r.locked_for(2000) == 500
    assert r.locked_for(3100) == 1000           # 2 steps above trigger
    t = ProfitLockTracker(r)
    assert not t.should_exit(3100)
    assert not t.should_exit(1500)               # peak still 3100 -> lock 1000
    assert t.should_exit(1000)


def test_profit_lock_parse_forms_and_validation():
    assert ProfitLockRule.parse("2000,500,500,250") == ProfitLockRule(2000, 500, 500, 250)
    assert ProfitLockRule.parse({"trigger": 2000, "lock": 500}) == ProfitLockRule(2000, 500, 0, 0)
    assert ProfitLockRule.parse(None) is None
    with pytest.raises(ValueError):
        ProfitLockRule(trigger=1000, lock=2000, step=0, increment=0)


def test_engine_exits_on_profit_lock_after_giveback():
    # Straddle decays (profit) then market trends away: lock must bank profit before time exit.
    panel = _day("2024-01-09", [21500, 21500, 21500, 21900])
    p = _params(sl_pct=1000.0, lot_size=65, profit_lock=ProfitLockRule(300, 100, 100, 50))
    row = TimedStraddleEngine(p).run(panel, EXP).iloc[0]
    assert row["exit_reason"] == "profit_lock"
    assert row["pnl"] > 0
