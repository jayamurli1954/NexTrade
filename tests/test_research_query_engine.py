"""B3 Research Query Engine + DVE-1 unit tests (fixtures)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.data_validation import DataValidationEngine, sha256_file
from research.factor_score_store import FactorScoreStore
from research.feature_store import FeatureStore
from research.research_query_engine import FactorQuery, ResearchQuery, ResearchQueryEngine
from research.research_service import ResearchSearchRequest, ResearchService


def _write_factor_fixture(root: Path) -> FactorScoreStore:
    store = FactorScoreStore(root)
    current = {
        "built_at": "2026-08-04T00:00:00+00:00",
        "symbols": {
            "AAA": {
                "fiscal_year": 2025,
                "scores": {
                    "quality": 85,
                    "growth": 75,
                    "value": 65,
                    "financial_health": 80,
                    "consistency": 70,
                    "overall_fundamental": 76,
                },
                "thesis": ["quality"],
            },
            "BBB": {
                "fiscal_year": 2025,
                "scores": {
                    "quality": 50,
                    "growth": 40,
                    "value": 90,
                    "financial_health": 60,
                    "consistency": 55,
                    "overall_fundamental": 55,
                },
                "thesis": [],
            },
            "CCC": {
                "fiscal_year": 2025,
                "scores": {
                    "quality": 90,
                    "growth": 80,
                    "value": 70,
                    "financial_health": 85,
                    "consistency": 88,
                    "overall_fundamental": 84,
                },
                "thesis": ["growth"],
            },
        },
    }
    store.save_current(current)
    hist_2022 = {
        "symbols": {
            "AAA": {"scores": {"quality": 60, "growth": 50, "value": 50, "financial_health": 50, "consistency": 50, "overall_fundamental": 52}},
            "CCC": {"scores": {"quality": 70, "growth": 60, "value": 60, "financial_health": 70, "consistency": 70, "overall_fundamental": 66}},
        }
    }
    store.save_historical_year(2022, hist_2022)
    store.save_historical_year(
        2025,
        {
            "symbols": {
                "AAA": current["symbols"]["AAA"],
                "BBB": current["symbols"]["BBB"],
                "CCC": current["symbols"]["CCC"],
            }
        },
    )
    return store


class TestResearchQueryEngine(unittest.TestCase):
    def test_quality_growth_value_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = _write_factor_fixture(root)
            eng = ResearchQueryEngine(factors=store, features=FeatureStore(root / "fs"))
            q = ResearchQuery(min_quality=80, min_growth=70, min_value=60, limit=50)
            r1 = eng.query(q)
            r2 = eng.query(q)
            syms1 = [i["symbol"] for i in r1.items]
            syms2 = [i["symbol"] for i in r2.items]
            self.assertEqual(syms1, syms2)
            self.assertEqual(set(syms1), {"AAA", "CCC"})
            self.assertNotIn("BBB", syms1)

    def test_factor_query_alias(self):
        self.assertIs(FactorQuery, ResearchQuery)

    def test_fiscal_year_as_of(self):
        with tempfile.TemporaryDirectory() as td:
            store = _write_factor_fixture(Path(td))
            eng = ResearchQueryEngine(factors=store, features=FeatureStore(Path(td) / "fs"))
            r = eng.query(ResearchQuery(fiscal_year=2022, min_quality=65, limit=10))
            syms = {i["symbol"] for i in r.items}
            self.assertIn("CCC", syms)
            self.assertNotIn("AAA", syms)  # quality 60 < 65

    def test_rsi_filter_with_panel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = _write_factor_fixture(root)
            fs = FeatureStore(root / "fs")
            fs.save_panel(
                pd.DataFrame(
                    [
                        {"date": "2026-08-01", "symbol": "AAA", "rsi": 30, "vix": 20, "quality": 85},
                        {"date": "2026-08-01", "symbol": "CCC", "rsi": 55, "vix": 20, "quality": 90},
                    ]
                )
            )
            eng = ResearchQueryEngine(factors=store, features=fs)
            r = eng.query(ResearchQuery(min_quality=80, max_rsi=40, as_of_date="2026-08-01", limit=10))
            syms = [i["symbol"] for i in r.items]
            self.assertEqual(syms, ["AAA"])

    def test_service_delegates_to_rqe(self):
        with tempfile.TemporaryDirectory() as td:
            store = _write_factor_fixture(Path(td))
            svc = ResearchService(factors=store, features=FeatureStore(Path(td) / "fs"))
            res = svc.search(
                ResearchSearchRequest(min_quality=80, min_growth=70, min_value=60, limit=10)
            )
            self.assertEqual(res.meta.get("delegated_to"), "research_query_engine")
            self.assertEqual({i["symbol"] for i in res.items}, {"AAA", "CCC"})


class TestDve1(unittest.TestCase):
    def test_duplicate_and_rsi(self):
        dve = DataValidationEngine()
        df = pd.DataFrame(
            [
                {"date": "2026-01-01", "symbol": "X", "rsi": 50, "quality": 80},
                {"date": "2026-01-01", "symbol": "X", "rsi": 50, "quality": 80},
            ]
        )
        rep = dve.validate_feature_panel(df)
        self.assertFalse(rep.ok)
        codes = {i.code for i in rep.issues}
        self.assertIn("DUPLICATE_ROWS", codes)

    def test_hash_stable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.txt"
            p.write_text("hello", encoding="utf-8")
            self.assertEqual(sha256_file(p), sha256_file(p))
            rep = DataValidationEngine().verify_repeatability([p])
            self.assertTrue(rep.ok)


if __name__ == "__main__":
    unittest.main()
