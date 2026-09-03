"""Paper terminal helpers (T2/T3) — preview overlay, local OHLC, no live broker."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_app.paper_capital_policy import qty_for_scrip_allocation
from trading_app.paper_terminal import (
    attach_plan_charge_preview,
    load_daily_ohlc,
    preview_from_payload,
    render_terminal_html,
)
from trading_app.trade_ticket_engine import TradeTicketEngine


class TestPaperTerminalPreview(unittest.TestCase):
    def test_fill_qty_uses_one_lakh_allocation(self):
        payload = {
            "entry_price": 1605.75,
            "target_price": 1800.0,
            "quantity": 10,
            "direction": "BUY",
            "profile_id": "ARROW",
        }
        out = preview_from_payload(payload)
        self.assertEqual(out["authority"], "PREVIEW_ONLY")
        self.assertEqual(out["fill_qty"], qty_for_scrip_allocation(1605.75))
        self.assertNotEqual(out["fill_qty"], 10)
        self.assertIn("V2 charges", out["v2_line"])
        self.assertIn("V3 slippage off", out["v3_line"])

    def test_v3_toggle(self):
        base = preview_from_payload({
            "entry_price": 1000, "target_price": 1020, "quantity": 50, "include_v3": False
        })
        with_v3 = preview_from_payload({
            "entry_price": 1000, "target_price": 1020, "quantity": 50, "include_v3": True
        })
        self.assertEqual(base["ticket"]["v2_charges"], with_v3["ticket"]["v2_charges"])
        self.assertGreater(with_v3["ticket"]["v3_slippage"], 0.0)

    def test_plan_overlay_does_not_mutate_engine(self):
        engine = TradeTicketEngine()
        plan = engine.create_trade_plan(
            "RELIANCE", "INTRADAY", "Momentum Breakout", "BUY",
            1400.0, 70, 1370.0, 1450.0,
        )
        charges = attach_plan_charge_preview(plan)
        self.assertEqual(plan.quantity, 70)
        self.assertEqual(charges["ticket"]["qty"], 70)
        summary = engine.generate_pre_trade_summary(plan)
        self.assertNotIn("charges_v2", summary)


class TestTerminalShell(unittest.TestCase):
    def test_html_is_paper_only(self):
        html = render_terminal_html()
        self.assertIn("PAPER ONLY", html)
        self.assertIn("/api/tariff/preview", html)
        self.assertNotIn("execute_live", html.lower())

    def test_local_ohlc_reliance(self):
        data = load_daily_ohlc("RELIANCE", bars=20)
        self.assertTrue(data["success"])
        self.assertGreaterEqual(len(data["bars"]), 10)
        self.assertGreater(data["bars"][-1]["close"], 0)

    def test_missing_symbol(self):
        data = load_daily_ohlc("NOT_A_REAL_SYMBOL_ZZZ")
        self.assertFalse(data["success"])
        self.assertEqual(data["bars"], [])


if __name__ == "__main__":
    unittest.main()
