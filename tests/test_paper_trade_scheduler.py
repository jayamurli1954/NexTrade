"""Unit tests for paper trade IST start-time scheduler."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_app import paper_trade_scheduler as sched
from trading_app.trade_ticket_engine import TradePlan, TrailingStopConfig, AutoExitConfig

IST = ZoneInfo("Asia/Kolkata")


def _plan():
    return TradePlan(
        trade_plan_id="tp1",
        symbol="BEL",
        trading_style="INTRADAY",
        strategy="Oversold Bounce",
        direction="BUY",
        entry_price=390.9,
        quantity=63,
        capital_required=24626.7,
        stop_loss_price=379.17,
        target_price=414.35,
        trailing_stop=TrailingStopConfig(enabled=True, trail_amount=20.0, current_trigger_price=370.9),
        auto_exit=AutoExitConfig(),
        max_loss_amount=739.0,
        potential_profit_amount=1477.0,
    )


class TestPaperTradeScheduler(unittest.TestCase):
    def setUp(self):
        with sched._lock:
            sched._orders.clear()

    def test_arm_before_start(self):
        now = datetime(2026, 7, 29, 9, 5, tzinfo=IST)  # Wednesday
        res = sched.arm_order(_plan(), "09:30", now=now)
        self.assertTrue(res["success"])
        self.assertEqual(res["order"]["status"], "ARMED")
        self.assertEqual(res["order"]["start_hhmm"], "09:30")

    def test_cannot_arm_before_0900(self):
        now = datetime(2026, 7, 29, 8, 50, tzinfo=IST)
        res = sched.arm_order(_plan(), "09:30", now=now)
        self.assertFalse(res["success"])
        self.assertIn("09:00", res["error"])

    def test_already_due_flag(self):
        now = datetime(2026, 7, 29, 10, 5, tzinfo=IST)
        res = sched.arm_order(_plan(), "09:30", now=now)
        self.assertFalse(res["success"])
        self.assertTrue(res.get("already_due"))

    def test_due_orders(self):
        now = datetime(2026, 7, 29, 9, 5, tzinfo=IST)
        sched.arm_order(_plan(), "09:30", now=now)
        due = sched.due_armed_orders(datetime(2026, 7, 29, 9, 31, tzinfo=IST))
        self.assertEqual(len(due), 1)

    def test_cancel(self):
        now = datetime(2026, 7, 29, 9, 5, tzinfo=IST)
        armed = sched.arm_order(_plan(), "10:00", now=now)
        sid = armed["order"]["schedule_id"]
        self.assertTrue(sched.cancel_order(sid)["success"])
        self.assertEqual(len(sched.due_armed_orders(datetime(2026, 7, 29, 10, 1, tzinfo=IST))), 0)

    def test_square_off_at_1515(self):
        before = datetime(2026, 7, 29, 15, 14, 59, tzinfo=IST)
        after = datetime(2026, 7, 29, 15, 15, 0, tzinfo=IST)
        self.assertFalse(sched.is_past_intraday_square_off(before))
        self.assertTrue(sched.is_past_intraday_square_off(after))
        self.assertTrue(sched.is_square_off_style("INTRADAY"))
        self.assertTrue(sched.is_square_off_style("SCALPING"))
        self.assertFalse(sched.is_square_off_style("SWING"))

    def test_position_needs_square_off(self):
        pos = {
            "status": "OPEN",
            "trading_style": "INTRADAY",
            "timestamp": "2026-07-29 09:15:07",
        }
        self.assertFalse(
            sched.position_needs_intraday_square_off(pos, datetime(2026, 7, 29, 15, 14, tzinfo=IST))
        )
        self.assertTrue(
            sched.position_needs_intraday_square_off(pos, datetime(2026, 7, 29, 15, 15, tzinfo=IST))
        )
        # Overnight leftover
        self.assertTrue(
            sched.position_needs_intraday_square_off(pos, datetime(2026, 7, 30, 10, 0, tzinfo=IST))
        )
        swing = {**pos, "trading_style": "SWING"}
        self.assertFalse(
            sched.position_needs_intraday_square_off(swing, datetime(2026, 7, 29, 15, 30, tzinfo=IST))
        )


if __name__ == "__main__":
    unittest.main()
