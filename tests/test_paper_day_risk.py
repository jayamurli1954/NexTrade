"""Tests for paper day profit/loss flatten + per-trade exit helpers."""

from __future__ import annotations

import unittest

from trading_app.paper_day_risk import (
    REASON_DAY_LOSS,
    REASON_DAY_PROFIT,
    REASON_STOP,
    REASON_TARGET,
    DayRiskLimits,
    collect_per_trade_exits,
    combined_day_pnl,
    day_flatten_reason,
    per_trade_exit_reason,
)


class TestPaperDayRisk(unittest.TestCase):
    def test_combined_pnl(self):
        self.assertEqual(combined_day_pnl(500, [400, 600]), 1500.0)

    def test_day_profit_flatten(self):
        self.assertEqual(day_flatten_reason(1500), REASON_DAY_PROFIT)
        self.assertEqual(day_flatten_reason(1499.99), None)

    def test_day_loss_flatten(self):
        self.assertEqual(day_flatten_reason(-2000), REASON_DAY_LOSS)
        self.assertEqual(day_flatten_reason(-1999.99), None)

    def test_custom_limits(self):
        lim = DayRiskLimits(profit_target_inr=1000, loss_limit_inr=500)
        self.assertEqual(day_flatten_reason(1000, lim), REASON_DAY_PROFIT)
        self.assertEqual(day_flatten_reason(-500, lim), REASON_DAY_LOSS)

    def test_buy_target_and_stop(self):
        self.assertEqual(
            per_trade_exit_reason(direction="BUY", ltp=110, target=110, stop_loss=90),
            REASON_TARGET,
        )
        self.assertEqual(
            per_trade_exit_reason(direction="BUY", ltp=90, target=110, stop_loss=90),
            REASON_STOP,
        )
        self.assertIsNone(
            per_trade_exit_reason(direction="BUY", ltp=100, target=110, stop_loss=90)
        )

    def test_sell_target_and_stop(self):
        self.assertEqual(
            per_trade_exit_reason(direction="SELL", ltp=90, target=90, stop_loss=110),
            REASON_TARGET,
        )
        self.assertEqual(
            per_trade_exit_reason(direction="SELL", ltp=110, target=90, stop_loss=110),
            REASON_STOP,
        )

    def test_collect_exits(self):
        rows = [
            {
                "position_id": "p1",
                "status": "OPEN",
                "direction": "BUY",
                "ltp": 2850,
                "target_raw": 2850,
                "stop_loss_raw": 2690,
            },
            {
                "position_id": "p2",
                "status": "OPEN",
                "direction": "BUY",
                "ltp": 2750,
                "target_raw": 2850,
                "stop_loss_raw": 2690,
            },
        ]
        hits = collect_per_trade_exits(rows)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], "p1")
        self.assertEqual(hits[0][2], REASON_TARGET)


if __name__ == "__main__":
    unittest.main()
