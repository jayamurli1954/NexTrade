"""Unit tests for NSE advance/decline breadth picker (no live network required)."""

from __future__ import annotations

import unittest

from trading_app import nse_market_breadth as breadth


class TestNseMarketBreadth(unittest.TestCase):
    def test_pick_total_market_preferred(self):
        payload = {
            "data": [
                {"index": "NIFTY 50", "advances": "31", "declines": "19", "unchanged": "0"},
                {"index": "NIFTY TOTAL MARKET", "advances": "504", "declines": "244", "unchanged": "4"},
                {"index": "NIFTY BANK", "advances": "13", "declines": "1", "unchanged": "0"},
            ]
        }
        picked = breadth._pick_breadth_row(payload)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked["index_name"], "NIFTY TOTAL MARKET")
        self.assertEqual(picked["advances"], 504)
        self.assertEqual(picked["declines"], 244)
        self.assertEqual(picked["unchanged"], 4)

    def test_fallback_nifty50(self):
        payload = {
            "data": [
                {"index": "NIFTY 50", "advances": 28, "declines": 22, "unchanged": 0},
            ]
        }
        picked = breadth._pick_breadth_row(payload)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked["index_name"], "NIFTY 50")
        self.assertEqual(picked["advances"], 28)

    def test_empty_payload(self):
        self.assertIsNone(breadth._pick_breadth_row({}))
        self.assertIsNone(breadth._pick_breadth_row({"data": []}))


if __name__ == "__main__":
    unittest.main()
