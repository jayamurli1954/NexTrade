"""Tests for Research Analytics Engine (B2) — fixtures, no network."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.analytics import (
    ResearchAnalyticsEngine,
    rae1_factor_distributions,
    rae3_factor_correlation,
    rae4_improvement_leaders,
    rae7_feature_coverage,
)
from research.factor_score_store import FactorScoreStore
from research.feature_store import FeatureStore


def _scores(q, g=50, v=50, h=50, c=50, o=None):
    return {
        "quality": q,
        "growth": g,
        "value": v,
        "financial_health": h,
        "consistency": c,
        "overall_fundamental": o if o is not None else q,
    }


class TestResearchAnalytics(unittest.TestCase):
    def test_distributions_and_corr(self):
        df = pd.DataFrame(
            [
                {"symbol": "A", **_scores(90, 80, 70, 60, 50)},
                {"symbol": "B", **_scores(40, 30, 20, 10, 5)},
                {"symbol": "C", **_scores(70, 60, 50, 40, 30)},
            ]
        )
        dist = rae1_factor_distributions(df)
        self.assertEqual(dist["universe_size"], 3)
        self.assertEqual(dist["factors"]["quality"]["n"], 3)
        self.assertIn("p50", dist["factors"]["quality"]["quantiles"])

        corr = rae3_factor_correlation(df)
        self.assertIn("matrix", corr)
        self.assertIsNotNone(corr["matrix"]["quality"]["overall_fundamental"])

    def test_improvement_leaders_no_lookahead(self):
        rows = []
        for fy, q in [(2022, 50), (2023, 60), (2024, 80), (2025, 90)]:
            rows.append({"symbol": "DEMO", "fiscal_year": fy, **_scores(q)})
        for fy, q in [(2022, 90), (2023, 70), (2024, 50), (2025, 40)]:
            rows.append({"symbol": "FADE", "fiscal_year": fy, **_scores(q)})
        long_df = pd.DataFrame(rows)
        leaders = rae4_improvement_leaders(long_df, metrics=("quality",), windows=(1, 3), top_n=5)
        top1 = leaders["leaders"]["quality"]["delta_1y"]["top"]
        self.assertTrue(any(r["symbol"] == "DEMO" for r in top1))
        # DEMO 1y: 90-80=+10; FADE 40-50=-10 → DEMO leads
        self.assertEqual(top1[0]["symbol"], "DEMO")
        self.assertEqual(top1[0]["from_fy"], 2024)
        self.assertEqual(top1[0]["to_fy"], 2025)

    def test_coverage(self):
        panel = pd.DataFrame(
            [
                {"symbol": "A", "date": "2026-01-01", "rsi": 50, "quality": 80, "pcr": None, "oi": None},
                {"symbol": "B", "date": "2026-01-01", "rsi": 40, "quality": None, "pcr": None, "oi": None},
            ]
        )
        cov = rae7_feature_coverage(panel)
        self.assertEqual(cov["coverage"]["rsi"], 100.0)
        self.assertEqual(cov["coverage"]["quality"], 50.0)
        self.assertEqual(cov["status"]["pcr"], "pending")

    def test_engine_build_all(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fund = root / "fundamentals"
            feat_root = root / "feature_store"
            out = root / "analytics"
            fs = FactorScoreStore(fund)
            # current
            fs.save_current(
                {
                    "built_at": "2026-08-04T00:00:00Z",
                    "config_version": "1.1",
                    "symbols": {
                        "AAA": {"symbol": "AAA", "fiscal_year": 2026, "scores": _scores(80)},
                        "BBB": {"symbol": "BBB", "fiscal_year": 2026, "scores": _scores(40)},
                    },
                }
            )
            for year, aq, bq in [(2024, 50, 70), (2025, 70, 50), (2026, 80, 40)]:
                fs.save_historical_year(
                    year,
                    {
                        "fiscal_year": year,
                        "symbols": {
                            "AAA": {"symbol": "AAA", "fiscal_year": year, "scores": _scores(aq)},
                            "BBB": {"symbol": "BBB", "fiscal_year": year, "scores": _scores(bq)},
                        },
                    },
                )
            feat = FeatureStore(feat_root)
            feat.save_panel(
                pd.DataFrame(
                    [
                        {"date": "2026-01-01", "symbol": "AAA", "rsi": 55, "quality": 80, "pcr": None, "oi": None},
                        {"date": "2026-01-01", "symbol": "BBB", "rsi": 45, "quality": 40, "pcr": None, "oi": None},
                    ]
                )
            )
            engine = ResearchAnalyticsEngine(factor_store=fs, feature_store=feat, out_dir=out)
            man = engine.build_all()
            self.assertIn("RAE-1", man["products"])
            self.assertTrue((out / "factor_distributions.json").exists())
            self.assertTrue((out / "factor_history_panel.csv").exists())
            self.assertTrue((out / "factor_correlation.json").exists())
            self.assertTrue((out / "improvement_leaders.json").exists())
            self.assertTrue((out / "feature_coverage.csv").exists())
            leaders = json.loads((out / "improvement_leaders.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(leaders["n_symbols"], 2)


if __name__ == "__main__":
    unittest.main()
