"""Paper ledger = base + today's net after charges (overall P&L excluded)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_app.broker_charges import estimate_equity_intraday_round_trip
from trading_app.paper_capital_ledger import (
    annotate_closed_trade_charges,
    displayed_paper_capital,
    infer_ledger_base_from_legacy_total,
    net_after_charges,
)


class TestNetAfterCharges(unittest.TestCase):
    def test_profit_is_reduced_by_charges(self):
        info = net_after_charges(gross_pnl=1000.0, entry=100.0, exit_px=110.0, qty=100)
        v2 = estimate_equity_intraday_round_trip(
            entry=100.0, exit_px=110.0, qty=100, include_slippage=False
        )
        self.assertEqual(info["est_charges"], round(v2.total, 2))
        self.assertEqual(info["net_pnl"], round(1000.0 - v2.total, 2))
        self.assertEqual(info["charges_breakdown"]["slippage"], 0.0)

    def test_loss_becomes_more_negative(self):
        info = net_after_charges(gross_pnl=-400.0, entry=110.0, exit_px=100.0, qty=100)
        self.assertLess(info["net_pnl"], -400.0)
        self.assertGreater(info["est_charges"], 0.0)


class TestDisplayedCapital(unittest.TestCase):
    def test_today_net_only_not_overall(self):
        base = 1_000_000.0
        today_net = 69.92
        overall_net = -3_443.97
        shown = displayed_paper_capital(base, today_net)
        self.assertEqual(shown, 1_000_069.92)
        self.assertNotAlmostEqual(shown, base + overall_net)

    def test_open_mtm_is_added_to_display(self):
        self.assertEqual(displayed_paper_capital(1_000_000.0, 69.92, 120.08), 1_000_190.00)

    def test_today_loss_reduces_display(self):
        self.assertEqual(displayed_paper_capital(1_000_000.0, -250.50), 999_749.50)

    def test_legacy_total_snaps_out_todays_net(self):
        self.assertEqual(infer_ledger_base_from_legacy_total(1_000_069.92), 1_000_000.0)
        self.assertEqual(infer_ledger_base_from_legacy_total(1_010_069.92), 1_010_000.0)
        self.assertEqual(infer_ledger_base_from_legacy_total(996_556.03), 1_000_000.0)

    def test_annotate_does_not_imply_overall(self):
        trade = {
            "status": "CLOSED",
            "pnl": 487.10,
            "entry_price": 100.0,
            "exit_price": 105.0,
            "quantity": 10,
        }
        row = annotate_closed_trade_charges(trade)
        self.assertIn("net_pnl", row)
        self.assertEqual(row["gross_pnl"], 487.10)


if __name__ == "__main__":
    unittest.main()
