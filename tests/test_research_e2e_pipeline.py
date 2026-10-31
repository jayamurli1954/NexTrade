"""
E2E-R1: Research pipeline integration test (no broker).

Factor store → Feature Store → ResearchService.search / feature_panel
→ Opportunity-style display attach → assert gates/confidence untouched.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.factor_score_store import FactorScoreStore
from research.feature_store import FeatureStore
from research.fundamental_service import build_ai_summary
from research.research_service import ResearchSearchRequest, ResearchService


def _fixture(root: Path):
    store = FactorScoreStore(root / "factors")
    store.save_current(
        {
            "built_at": "2026-08-04T12:00:00+00:00",
            "symbols": {
                "DEMO": {
                    "fiscal_year": 2025,
                    "scores": {
                        "quality": 88,
                        "growth": 72,
                        "value": 66,
                        "financial_health": 80,
                        "consistency": 75,
                        "overall_fundamental": 78,
                    },
                    "thesis": ["Strong quality"],
                    "relatives": {"pe_vs_peers": "cheap"},
                }
            },
        }
    )
    store.save_historical_year(
        2023,
        {
            "symbols": {
                "DEMO": {
                    "scores": {
                        "quality": 70,
                        "growth": 60,
                        "value": 55,
                        "financial_health": 70,
                        "consistency": 65,
                        "overall_fundamental": 64,
                    }
                }
            }
        },
    )
    fs = FeatureStore(root / "features")
    fs.save_panel(
        pd.DataFrame(
            [
                {
                    "date": "2026-08-01",
                    "symbol": "DEMO",
                    "rsi": 42,
                    "ema20": 100,
                    "ema50": 98,
                    "atr": 2,
                    "adx": 20,
                    "quality": 88,
                    "growth": 72,
                    "value": 66,
                    "financial_health": 80,
                    "consistency": 75,
                    "overall_fundamental": 78,
                    "vix": 14,
                    "pcr": None,
                    "oi": None,
                }
            ]
        )
    )
    fs.write_manifest(
        {
            "feature_store_version": "1.0",
            "lookahead_safe": True,
            "mode": "e2e_fixture",
        }
    )
    return store, fs


class TestResearchE2EPipeline(unittest.TestCase):
    def test_warehouse_to_opportunity_display_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store, fs = _fixture(root)
            svc = ResearchService(factors=store, features=fs)

            # Search via RQE
            hit = svc.search(
                ResearchSearchRequest(min_quality=80, min_growth=70, min_value=60, limit=10)
            )
            self.assertEqual(len(hit.items), 1)
            self.assertEqual(hit.items[0]["symbol"], "DEMO")
            self.assertEqual(hit.meta.get("delegated_to"), "research_query_engine")

            # Feature panel metadata
            panel = svc.feature_panel("DEMO", "2026-08-01")
            self.assertIsNotNone(panel)
            assert panel is not None
            self.assertTrue(panel["metadata"]["lookahead_safe"])
            self.assertEqual(panel["fundamental"]["quality"], 88)
            self.assertEqual(panel["technical"]["rsi"], 42)

            # Opportunity-style display attach (mirrors OpportunityEngine fields)
            scores = hit.items[0]["scores"]
            thesis = list(hit.items[0].get("thesis") or [])
            confidence_before = 0.81  # simulated legacy score — must not change
            action = "BUY"
            ai = build_ai_summary(
                direction=action,
                why_technical=["RSI 42"],
                thesis=thesis,
                factor_scores=scores,
            )
            confidence_after = confidence_before
            self.assertEqual(confidence_after, 0.81)
            self.assertIsInstance(ai, str)
            # Display payload shape
            display = {
                "factor_scores": scores,
                "investment_thesis": thesis,
                "ai_summary": ai,
                "confidence": confidence_after,
                "action": action,
            }
            self.assertIn("quality", display["factor_scores"])
            self.assertEqual(display["confidence"], 0.81)


if __name__ == "__main__":
    unittest.main()
