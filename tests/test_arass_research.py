"""Unit tests for ARASS research engine (no network)."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.arass.costs import estimate_straddle_round_trip_cost
from research.arass.definition import ARASS_PARAMS, build_arass_hypothesis, build_arass_strategy_draft
from research.arass.engine import ArassBacktestEngine
from research.arass.filters import evaluate_filters
from research.arass.indicators import atm_strike, black_scholes_price


def _synthetic_panel(n_days: int = 40, start: str = "2024-01-02") -> pd.DataFrame:
    """Build a quiet range-bound panel that should allow some ARASS entries."""
    days = pd.bdate_range(start=start, periods=n_days, freq="C")
    rows = []
    spot = 22000.0
    vix = 14.5
    rng = np.random.default_rng(42)
    for d in days:
        # tiny drift / noise
        spot *= 1.0 + float(rng.normal(0, 0.0015))
        open_px = spot * (1.0 + float(rng.normal(0, 0.0005)))
        # keep OR and day range tight (<1%)
        high = open_px * 1.004
        low = open_px * 0.996
        close = open_px * (1.0 + float(rng.normal(0, 0.001)))
        # 5m bars 09:15–15:30
        for minute in range(9 * 60 + 15, 15 * 60 + 30, 5):
            t = pd.Timestamp(d) + pd.Timedelta(hours=minute // 60, minutes=minute % 60)
            # flat-ish path
            frac = (minute - (9 * 60 + 15)) / (6 * 60 + 15)
            px = open_px + (close - open_px) * frac
            rows.append(
                {
                    "datetime": t,
                    "open": px,
                    "high": min(high, px * 1.001),
                    "low": max(low, px * 0.999),
                    "close": px,
                    "volume": 1000.0,
                    "vix": vix,
                }
            )
    df = pd.DataFrame(rows).set_index("datetime")
    return df


class TestArassBasics(unittest.TestCase):
    def test_definition(self):
        h = build_arass_hypothesis()
        d = build_arass_strategy_draft()
        self.assertEqual(h.hypothesis_id, "H-ARASS-V1")
        self.assertEqual(d.strategy_id, "ARASS")
        self.assertEqual(d.family, "VOLATILITY")

    def test_bs_atm_positive(self):
        px = black_scholes_price(22000, 22000, 3 / 365, 0.14, 0.065, "CE")
        self.assertGreater(px, 0)
        self.assertEqual(atm_strike(22037, 50), 22050)

    def test_filters_reject_high_vix(self):
        ts = pd.Timestamp("2024-01-03 10:35:00")  # Wednesday
        fr = evaluate_filters(
            ts=ts,
            spot=22000,
            vwap=22000,
            ema20=22000,
            ema50=22005,
            adx_val=12,
            vix=25,
            gap_pct=0.1,
            opening_range_pct=0.4,
            params=ARASS_PARAMS,
            event_dates=set(),
        )
        self.assertFalse(fr.allowed)
        self.assertIn("vix_out_of_band", fr.reasons)

    def test_cost_positive(self):
        c = estimate_straddle_round_trip_cost(
            entry_ce=100, entry_pe=100, exit_ce=80, exit_pe=80, qty=50, params=ARASS_PARAMS
        )
        self.assertGreater(c.total, 0)

    def test_engine_runs_offline(self):
        panel = _synthetic_panel()
        engine = ArassBacktestEngine(params=ARASS_PARAMS, event_dates=set())
        draft = build_arass_strategy_draft()
        result = engine.run(draft, {"panel": panel, "provenance": "synthetic_test"})
        self.assertEqual(result.engine_name, "NEXTRADE_ARASS_RESEARCH_V1")
        self.assertIn("arass_metrics", result.extras)
        # May or may not trade depending on EMA warmup; should not crash
        self.assertIsInstance(result.trades, list)


if __name__ == "__main__":
    unittest.main()
