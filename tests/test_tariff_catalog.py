"""Tariff catalog (T1) — Arrow published example + statutory vs brokerage split."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_app.broker_charges import AngelOneEquityIntradayCharges
from trading_app.tariff_catalog import (
    AUTHORITY,
    DEFAULT_PROFILE_ID,
    PROFILE_FLAT20,
    brokerage_for_order,
    preview_round_trip,
    resolve_segment,
)


class TestArrowPublishedExample(unittest.TestCase):
    """arrow.trade/pricing HDFC MIS worked example (buy 10 @ 1605.75, sell @ 1800)."""

    def test_hdfc_round_trip_v2_matches_published_total(self):
        prev = preview_round_trip(
            entry=1605.75,
            exit_px=1800.0,
            qty=10,
            direction="BUY",
            segment="EQUITY_INTRADAY",
            profile_id="ARROW",
        )
        self.assertEqual(prev.authority, AUTHORITY)
        self.assertEqual(prev.brokerage, 10.22)
        self.assertEqual(prev.stt, 4.50)
        self.assertEqual(prev.stamp, 0.48)
        self.assertAlmostEqual(prev.v2_charges, 18.31, delta=0.05)
        self.assertEqual(prev.v3_slippage, 0.0)

    def test_v3_is_opt_in_and_not_in_v2(self):
        off = preview_round_trip(entry=1605.75, exit_px=1800.0, qty=10, include_v3=False)
        on = preview_round_trip(entry=1605.75, exit_px=1800.0, qty=10, include_v3=True)
        self.assertEqual(off.v2_charges, on.v2_charges)
        self.assertGreater(on.v3_slippage, 0.0)
        self.assertGreater(on.v3_charges, on.v2_charges)


class TestBrokerageProfiles(unittest.TestCase):
    def test_min_flat_or_pct_binds_below_cap(self):
        rule = PROFILE_FLAT20.equity_intraday
        self.assertEqual(brokerage_for_order(rule, 10_000), 20.0)

    def test_arrow_small_ticket_uses_pct(self):
        prev = preview_round_trip(
            entry=1000.0, exit_px=1010.0, qty=10, profile_id="ARROW"
        )
        # 0.03% of 10_000 = 3.00 per order < ₹20
        self.assertEqual(prev.brokerage, 6.03)  # 3.00 + 3.03

    def test_arrow_large_ticket_caps_at_20(self):
        prev = preview_round_trip(
            entry=1400.0, exit_px=1410.0, qty=100, profile_id="ARROW"
        )
        self.assertEqual(prev.brokerage, 40.0)

    def test_flat20_always_40_round_trip(self):
        prev = preview_round_trip(
            entry=1000.0, exit_px=1010.0, qty=10, profile_id="FLAT20"
        )
        self.assertEqual(prev.brokerage, 40.0)


class TestDirectionAwareLegs(unittest.TestCase):
    def test_short_stt_on_entry_sell(self):
        long_leg = preview_round_trip(
            entry=1383.3, exit_px=1374.2, qty=50, direction="BUY"
        )
        short_leg = preview_round_trip(
            entry=1383.3, exit_px=1374.2, qty=50, direction="SELL"
        )
        self.assertGreater(short_leg.stt, 0)
        self.assertNotEqual(short_leg.stt, long_leg.stt)
        self.assertNotEqual(short_leg.stamp, long_leg.stamp)


class TestSegmentResolve(unittest.TestCase):
    def test_options_style(self):
        self.assertEqual(resolve_segment(None, "OPTIONS_BUYING").value, "OPTIONS")

    def test_mis_alias(self):
        self.assertEqual(resolve_segment("MIS").value, "EQUITY_INTRADAY")


class TestLedgerDefaultsUntouched(unittest.TestCase):
    def test_angel_engine_defaults_frozen(self):
        m = AngelOneEquityIntradayCharges()
        self.assertEqual(m.broker, "ANGEL_ONE")
        self.assertEqual(m.brokerage_per_order_inr, 20.0)
        self.assertEqual(m.exchange_txn_pct, 0.00345)
        self.assertEqual(m.slippage_pct, 0.05)
        self.assertEqual(DEFAULT_PROFILE_ID, "ARROW")


if __name__ == "__main__":
    unittest.main()
