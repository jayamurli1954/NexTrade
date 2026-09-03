"""Unit tests for pre-market brief helpers."""

from __future__ import annotations

import unittest
from datetime import time as dt_time

from trading_app.premarket_brief import (
    classify_session_window,
    derive_market_bias,
    focus_from_analyzer_signals,
    focus_from_watchlist_movers,
)


class TestPremarketBrief(unittest.TestCase):
    def test_session_windows(self):
        w, _ = classify_session_window(dt_time(8, 0), weekday=4, market_open=False)
        self.assertEqual(w, "PRE_MARKET")
        w, _ = classify_session_window(dt_time(11, 0), weekday=4, market_open=True)
        self.assertEqual(w, "MARKET_OPEN")
        w, _ = classify_session_window(dt_time(11, 0), weekday=5, market_open=False)
        self.assertEqual(w, "WEEKEND")

    def test_bias_sideways_and_bullish(self):
        bias, _ = derive_market_bias(0.10, -0.05, 14.0)
        self.assertEqual(bias, "SIDEWAYS / RANGE")
        bias, detail = derive_market_bias(0.80, 0.40, 13.0, advances=500, declines=200, breadth_live=True)
        self.assertEqual(bias, "BULLISH BIAS")
        self.assertIn("500/200", detail)

    def test_focus_from_signals_not_demo(self):
        signals = [
            {"symbol": "BEL", "action": "BUY", "confidence": 0.88, "reason": "Oversold Bounce"},
            {"symbol": "INFY", "action": "SELL", "confidence": 0.70, "reason": "Breakdown"},
            {"symbol": "HOLDME", "action": "HOLD", "confidence": 0.99, "reason": "ignore"},
        ]
        focus = focus_from_analyzer_signals(signals)
        self.assertEqual([f["symbol"] for f in focus], ["BEL", "INFY"])
        self.assertNotIn("RELIANCE", [f["symbol"] for f in focus])

    def test_watchlist_movers(self):
        live = {
            "AAA": {"ltp": 100, "change_pct": 3.5, "source": "ANGEL_WEBSOCKET"},
            "BBB": {"ltp": 200, "change_pct": -2.0, "source": "ANGEL_WEBSOCKET"},
        }
        focus = focus_from_watchlist_movers(["AAA", "BBB"], live)
        self.assertEqual(focus[0]["symbol"], "AAA")
        self.assertEqual(focus[0]["direction"], "BUY")


if __name__ == "__main__":
    unittest.main()
