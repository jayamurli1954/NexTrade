"""Tests for Sprint B1a/B1b Feature Registry, PIT backfill, feature_panel metadata."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.data_validation import DataValidationEngine
from research.feature_registry import FeatureRegistry, bootstrap_registry
from research.feature_store import FeatureStore
from research.factor_score_store import FactorScoreStore
from research.research_service import ResearchService


class TestFeatureRegistry(unittest.TestCase):
    def test_bootstrap_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            reg = bootstrap_registry(path)
            self.assertIn("quality", reg.entries)
            self.assertIn("rsi", reg.entries)
            self.assertEqual(reg.entries["quality"]["version"], "1.1")
            self.assertTrue(reg.provenance_label("quality").startswith("fundamental_factor_engine@"))


class TestFeatureStorePit(unittest.TestCase):
    def test_pit_no_lookahead_and_panel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # minimal factor store layout
            fund = root / "fundamentals"
            hist = fund / "historical"
            cur = fund / "current"
            hist.mkdir(parents=True)
            cur.mkdir(parents=True)

            def _year_payload(year, quality):
                return {
                    "fiscal_year": year,
                    "symbols": {
                        "DEMO": {
                            "symbol": "DEMO",
                            "fiscal_year": year,
                            "scores": {
                                "quality": quality,
                                "growth": 50,
                                "value": 50,
                                "financial_health": 50,
                                "consistency": 50,
                                "overall_fundamental": quality,
                            },
                        }
                    },
                }

            (hist / "2024.json").write_text(json.dumps(_year_payload(2024, 60)), encoding="utf-8")
            (hist / "2025.json").write_text(json.dumps(_year_payload(2025, 80)), encoding="utf-8")
            (cur / "factor_scores.json").write_text(
                json.dumps(
                    {
                        "built_at": "2026-08-04T00:00:00+00:00",
                        "config_version": "1.1",
                        "symbols": _year_payload(2026, 90)["symbols"],
                    }
                ),
                encoding="utf-8",
            )

            fstore = FactorScoreStore(fund)
            feat = FeatureStore(root / "feature_store")
            bootstrap_registry(feat.registry_path)
            man = feat.backfill_fundamentals_pit(
                factor_store=fstore,
                as_of_dates=["2024-06-01", "2025-06-01", "2026-08-04"],
            )
            self.assertTrue(man.get("lookahead_safe"))
            self.assertGreater(man.get("rows", 0), 0)

            # Before FY2025 end, should still see 2024 quality 60
            row_early = feat.get_row("DEMO", "2024-06-01")
            self.assertIsNotNone(row_early)
            self.assertEqual(row_early["quality"], 60)

            # After Mar 2025, quality 80
            row_mid = feat.get_row("DEMO", "2025-06-01")
            self.assertEqual(row_mid["quality"], 80)

            svc = ResearchService(factors=fstore, features=feat)
            panel = svc.feature_panel("DEMO", "2025-06-01")
            self.assertIsNotNone(panel)
            assert panel is not None
            self.assertEqual(panel["fundamental"]["quality"], 80)
            self.assertIn("metadata", panel)
            self.assertTrue(panel["metadata"]["lookahead_safe"])
            self.assertEqual(panel["metadata"]["feature_store_version"], "1.0")
            self.assertIn("feature_versions", panel["metadata"])
            self.assertIn("provenance", panel["metadata"])


class TestTechnicalCompute(unittest.TestCase):
    def test_compute_technical_frame(self):
        import numpy as np
        import pandas as pd
        from research.technical_features import compute_technical_frame

        idx = pd.date_range("2024-01-01", periods=80, freq="B")
        close = pd.Series(np.linspace(100, 140, len(idx)), index=idx)
        high = close + 1
        low = close - 1
        ohlc = pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 1000}, index=idx)
        tech = compute_technical_frame(ohlc)
        self.assertIn("rsi", tech.columns)
        self.assertFalse(tech["ema20"].dropna().empty)
        self.assertFalse(tech["atr"].dropna().empty)
        last = tech.dropna(subset=["rsi", "ema20"]).iloc[-1]
        self.assertGreaterEqual(float(last["rsi"]), 0)
        self.assertLessEqual(float(last["rsi"]), 100)


class TestDataValidation(unittest.TestCase):
    def test_coverage_stats(self):
        import pandas as pd

        df = pd.DataFrame(
            [
                {"date": "2026-01-01", "symbol": "A", "quality": 80, "rsi": 50, "pcr": None, "oi": None},
                {"date": "2026-01-01", "symbol": "B", "quality": 70, "rsi": 40, "pcr": None, "oi": None},
            ]
        )
        rep = DataValidationEngine().validate_feature_panel(df)
        self.assertTrue(rep.ok)
        self.assertIn("coverage_pct", rep.stats)
        self.assertEqual(rep.stats["coverage_pct"]["quality"], 100.0)


if __name__ == "__main__":
    unittest.main()
