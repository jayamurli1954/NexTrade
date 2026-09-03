"""Unit tests for CAL-1 calendar download helpers (no network)."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.download_nifty_options import select_calendar_expiries, strike_grid


class TestCalendarDownloadPlan(unittest.TestCase):
    def test_select_near_mid_far(self):
        cands = [
            date(2024, 1, 4),
            date(2024, 1, 11),
            date(2024, 1, 18),
            date(2024, 1, 25),
            date(2024, 2, 29),
            date(2024, 3, 28),
        ]
        sel = select_calendar_expiries(date(2024, 1, 2), cands, min_far_dte=28)
        self.assertEqual(sel[0], date(2024, 1, 4))
        self.assertEqual(sel[1], date(2024, 1, 11))
        self.assertIn(date(2024, 2, 29), sel)
        self.assertGreaterEqual((sel[-1] - date(2024, 1, 2)).days, 28)

    def test_strike_grid_width(self):
        g = strike_grid(22000.0, 50.0, 4)
        self.assertEqual(len(g), 9)
        self.assertEqual(g[0], 21800.0)
        self.assertEqual(g[4], 22000.0)
        self.assertEqual(g[-1], 22200.0)


if __name__ == "__main__":
    unittest.main()
