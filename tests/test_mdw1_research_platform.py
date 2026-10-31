"""Tests for MDW-1 options lookup + Research Platform scaffolds."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.arass.options_store import OptionsStore
from research.feature_store import FeatureStore
from research.research_service import ResearchSearchRequest, ResearchService


def _tiny_options_csv(path: Path) -> None:
    rows = [
        # CE/PE for expiry 2024-01-04, strikes 21500 and 21550
        dict(date="2024-01-02", expiry="2024-01-04", strike=21500, option_type="CE", open=100, high=120, low=90, close=110, volume=1, oi=1, symbol="NIFTY"),
        dict(date="2024-01-02", expiry="2024-01-04", strike=21500, option_type="PE", open=95, high=115, low=85, close=105, volume=1, oi=1, symbol="NIFTY"),
        dict(date="2024-01-02", expiry="2024-01-04", strike=21550, option_type="CE", open=80, high=90, low=70, close=85, volume=1, oi=1, symbol="NIFTY"),
        dict(date="2024-01-02", expiry="2024-01-04", strike=21550, option_type="PE", open=120, high=130, low=110, close=125, volume=1, oi=1, symbol="NIFTY"),
        dict(date="2024-01-03", expiry="2024-01-04", strike=21500, option_type="CE", open=100, high=120, low=90, close=112, volume=1, oi=1, symbol="NIFTY"),
        dict(date="2024-01-03", expiry="2024-01-04", strike=21500, option_type="PE", open=95, high=115, low=85, close=108, volume=1, oi=1, symbol="NIFTY"),
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


class TestOptionsStoreMdw1(unittest.TestCase):
    def test_soft_strike_and_on_or_before(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opts.csv"
            _tiny_options_csv(path)
            store = OptionsStore.load(path)
            # exact strike
            hit = store.straddle(
                symbol="NIFTY",
                asof=pd.Timestamp("2024-01-03 10:15"),
                expiry=pd.Timestamp("2024-01-04 15:30"),
                strike=21500,
            )
            self.assertIsNotNone(hit)
            assert hit is not None
            self.assertEqual(hit, (112.0, 108.0))

            # nearest strike (request 21525 → 21500 or 21550)
            near = store.straddle(
                symbol="NIFTY",
                asof=pd.Timestamp("2024-01-02"),
                expiry=pd.Timestamp("2024-01-04"),
                strike=21525,
                allow_nearest_strike=True,
            )
            self.assertIsNotNone(near)

            # on_or_before: request Jan 5 after last bar → use Jan 3
            fill = store.straddle(
                symbol="NIFTY",
                asof=pd.Timestamp("2024-01-05"),
                expiry=pd.Timestamp("2024-01-04"),
                strike=21500,
                asof_policy="on_or_before",
            )
            self.assertEqual(fill, (112.0, 108.0))


class TestResearchPlatformScaffold(unittest.TestCase):
    def test_feature_store_upsert(self):
        with tempfile.TemporaryDirectory() as td:
            fs = FeatureStore(Path(td))
            fs.upsert_factor_snapshot(
                "2026-08-04",
                {"TCS": {"quality": 90, "growth": 40, "value": 80, "financial_health": 95, "consistency": 90, "overall_fundamental": 80}},
            )
            panel = fs.load_panel()
            self.assertEqual(len(panel), 1)
            self.assertEqual(panel.iloc[0]["symbol"], "TCS")

    def test_research_service_search_filters(self):
        # Uses live factor store if present; otherwise empty ok
        svc = ResearchService()
        res = svc.search(ResearchSearchRequest(min_quality=80, min_overall=70, limit=5))
        self.assertIsInstance(res.items, list)
        self.assertIn("source", res.meta)
        for item in res.items:
            self.assertGreaterEqual(float(item["scores"]["quality"]), 80)
            self.assertGreaterEqual(float(item["scores"]["overall_fundamental"]), 70)


if __name__ == "__main__":
    unittest.main()
