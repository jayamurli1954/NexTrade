"""Unit tests for CAL-2 calendar spread research (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.arass.options_store import OptionsStore
from research.calendar_spread.costs import calendar_pnl_pts, estimate_calendar_311_round_trip_cost
from research.calendar_spread.definition import CAL_PARAMS
from research.calendar_spread.engine import CalendarSpreadEngine
from research.calendar_spread.expiries import ExpiryTriplet, pick_expiry_triplet
from research.calendar_spread.signals import band_for_mode, premium_differential
from research.calendar_spread.zone import overnight_gap_pct, select_strike, zone_lean


class TestZoneAndGap(unittest.TestCase):
    def test_zone_thirds(self):
        self.assertEqual(zone_lean(190, 200, 100), "CE")  # upper
        self.assertEqual(zone_lean(110, 200, 100), "PE")  # lower
        self.assertIsNone(zone_lean(150, 200, 100))  # middle

    def test_gap_skip_threshold(self):
        self.assertGreaterEqual(overnight_gap_pct(101, 100), 0.80)
        self.assertLess(overnight_gap_pct(100.5, 100), 0.80)

    def test_strike_offset(self):
        # CE lean toward extreme → +1 step
        self.assertEqual(
            select_strike(22120, "CE", zone_high=22500, zone_low=21500, strike_step=50),
            22150,
        )


class TestSignals(unittest.TestCase):
    def test_far_minus_near_default_band_amended(self):
        self.assertEqual(CAL_PARAMS.pts_band_lo, 200.0)
        self.assertEqual(CAL_PARAMS.pts_band_hi, 300.0)
        lo, hi, ex = band_for_mode("far_minus_near")
        self.assertEqual((lo, hi, ex), (200.0, 300.0, 150.0))

    def test_next_minus_near_keeps_70_80(self):
        lo, hi, ex = band_for_mode("next_minus_near")
        self.assertEqual((lo, hi, ex), (70.0, 80.0, 40.0))
        self.assertEqual(premium_differential(near=100, nxt=175, far=350, mode="next_minus_near"), 75.0)
        self.assertEqual(premium_differential(near=100, nxt=175, far=350, mode="far_minus_near"), 250.0)


class TestCosts(unittest.TestCase):
    def test_pnl_pts_long_far_short_nears(self):
        pts = calendar_pnl_pts(
            entry_near=100,
            entry_next=120,
            entry_far=180,
            mark_near=90,
            mark_next=110,
            mark_far=185,
        )
        # 3*(5) + 1*(10) + 1*(10) = 35
        self.assertEqual(pts, 35.0)

    def test_round_trip_cost_positive(self):
        cost = estimate_calendar_311_round_trip_cost(
            entry_near=100,
            entry_next=120,
            entry_far=180,
            exit_near=90,
            exit_next=110,
            exit_far=185,
            lot_size=65,
        )
        self.assertGreater(cost.total, 0)
        self.assertEqual(cost.slippage, 0.0)  # V2 default


class TestExpiryPick(unittest.TestCase):
    def test_triplet(self):
        asof = pd.Timestamp("2024-06-03")
        expiries = [
            pd.Timestamp("2024-06-06"),  # ~3d near
            pd.Timestamp("2024-06-13"),  # ~10d next
            pd.Timestamp("2024-07-25"),  # ~52d far
        ]
        trip = pick_expiry_triplet(expiries, asof=asof, params=CAL_PARAMS)
        self.assertIsInstance(trip, ExpiryTriplet)
        self.assertEqual(trip.near, pd.Timestamp("2024-06-06"))
        self.assertEqual(trip.next_weekly, pd.Timestamp("2024-06-13"))
        self.assertEqual(trip.far, pd.Timestamp("2024-07-25"))


def _synthetic_spot(n: int = 80, start: str = "2024-01-02") -> pd.DataFrame:
    days = pd.bdate_range(start=start, periods=n, freq="C")
    rng = np.random.default_rng(7)
    spot = 22000.0
    rows = []
    for d in days:
        spot *= 1.0 + float(rng.normal(0, 0.002))
        o = spot * (1.0 + float(rng.normal(0, 0.0003)))
        h = o * 1.006
        l = o * 0.994
        c = o * (1.0 + float(rng.normal(0, 0.001)))
        rows.append({"open": o, "high": h, "low": l, "close": c})
    return pd.DataFrame(rows, index=days)


def _synthetic_options(spot: pd.DataFrame) -> OptionsStore:
    """Build CE/PE premiums so far−near sits in 70–80 pts often."""
    rows = []
    for day in spot.index:
        day = pd.Timestamp(day).normalize()
        px = float(spot.loc[day, "close"])
        strike = round(px / 50.0) * 50.0
        # three expiries: +3d, +10d, +35d
        for dte, base in ((3, 100.0), (10, 130.0), (35, 350.0)):
            exp = day + pd.Timedelta(days=dte)
            # far−near ≈ 250 (amended CAL-0 band); next−near ≈ 30
            for otype in ("CE", "PE"):
                prem = base
                rows.append(
                    {
                        "date": day,
                        "expiry": exp,
                        "strike": strike,
                        "option_type": otype,
                        "open": prem,
                        "high": prem,
                        "low": prem,
                        "close": prem,
                        "volume": 100,
                        "oi": 100,
                        "symbol": "NIFTY",
                    }
                )
                # also store ±50 strikes
                for off in (-50, 50):
                    rows.append(
                        {
                            "date": day,
                            "expiry": exp,
                            "strike": strike + off,
                            "option_type": otype,
                            "open": prem,
                            "high": prem,
                            "low": prem,
                            "close": prem,
                            "volume": 100,
                            "oi": 100,
                            "symbol": "NIFTY",
                        }
                    )
    path = ROOT / "research" / "data" / "options" / "_test_cal2_tmp.csv"
    store = OptionsStore.empty(path)
    store.merge(pd.DataFrame(rows))
    return store


class TestEngineSmoke(unittest.TestCase):
    def test_engine_runs_and_can_trade(self):
        spot = _synthetic_spot()
        store = _synthetic_options(spot)
        # Widen zone so lean triggers: push last 25 days into a clear uptrend
        spot = spot.copy()
        for i, idx in enumerate(spot.index):
            spot.loc[idx, "high"] = float(spot.loc[idx, "close"]) * 1.01
            spot.loc[idx, "low"] = float(spot.loc[idx, "close"]) * 0.99
            if i > 40:
                spot.loc[idx, "close"] = float(spot.iloc[i - 1]["close"]) * 1.003
                spot.loc[idx, "open"] = float(spot.loc[idx, "close"]) * 0.999
                spot.loc[idx, "high"] = float(spot.loc[idx, "close"]) * 1.004
                spot.loc[idx, "low"] = float(spot.loc[idx, "close"]) * 0.996

        engine = CalendarSpreadEngine(CAL_PARAMS)
        report = engine.run(spot, store)
        self.assertIn("metrics", report)
        self.assertEqual(report["engine_name"], "NEXTRADE_CALENDAR_SPREAD_RESEARCH_V1")
        self.assertIn("not certified", report["notes"].lower())
        # With synthetic 75pt differential, expect some band candidates
        self.assertGreaterEqual(report["filter_stats"]["pts_band_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
