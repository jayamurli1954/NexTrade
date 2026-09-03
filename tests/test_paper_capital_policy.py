"""Unit tests for paper capital allocation policy."""

from __future__ import annotations

import unittest

from trading_app.paper_capital_policy import (
    PAPER_DEPLOYABLE_CAPITAL,
    PAPER_PER_SCRIP_CAPITAL,
    can_open_paper_position,
    qty_for_scrip_allocation,
)
from trading_app.opportunity_engine import _qty_for_entry


class TestPaperCapitalPolicy(unittest.TestCase):
    def test_qty_examples(self):
        self.assertEqual(qty_for_scrip_allocation(200), 500)
        self.assertEqual(qty_for_scrip_allocation(1000), 100)
        self.assertEqual(_qty_for_entry(200), 500)

    def test_per_scrip_cap(self):
        ok, _ = can_open_paper_position(0, 0, PAPER_PER_SCRIP_CAPITAL)
        self.assertTrue(ok)
        ok, msg = can_open_paper_position(0, 0, PAPER_PER_SCRIP_CAPITAL + 1)
        self.assertFalse(ok)
        self.assertIn("Per-scrip", msg)

    def test_deployable_cap(self):
        ok, _ = can_open_paper_position(4, 400_000, 100_000)
        self.assertTrue(ok)
        ok, msg = can_open_paper_position(4, 490_000, 20_000)
        self.assertFalse(ok)
        self.assertIn("Deployable", msg)
        ok, msg = can_open_paper_position(5, 0, 10_000)
        self.assertFalse(ok)
        self.assertIn("Max 5", msg)

    def test_deployable_total(self):
        ok, msg = can_open_paper_position(0, PAPER_DEPLOYABLE_CAPITAL, 1)
        self.assertFalse(ok)
        self.assertIn("Deployable", msg)


if __name__ == "__main__":
    unittest.main()
