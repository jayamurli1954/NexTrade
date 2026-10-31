"""Tests for local fundamentals loader + analyzer wiring (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analyzer.fundamentals_analyzer import FundamentalsAnalyzer
from research.fundamentals_loader import (
    build_fundamentals_highlights,
    load_fundamentals_from_store,
)
from research.fundamentals_store import FundamentalsStore


def _sample_payload(symbol: str = "DEMO") -> dict:
    return {
        "symbol": symbol,
        "view": "consolidated",
        "scraped_at": "2026-01-01T00:00:00+00:00",
        "sections": {
            "profit_loss": {
                "table": {
                    "period_type": "annual",
                    "headers": ["Mar 2024", "Mar 2025"],
                    "rows": [
                        {"label": "Sales", "values": [1000.0, 1150.0]},
                        {"label": "Net Profit", "values": [100.0, 120.0]},
                    ],
                }
            },
            "balance_sheet": {
                "period_type": "annual",
                "headers": ["Mar 2025"],
                "rows": [
                    {"label": "Borrowings", "values": [200.0]},
                    {"label": "Equity Capital", "values": [50.0]},
                    {"label": "Reserves", "values": [350.0]},
                ],
            },
            "pros_cons": {
                "key_metrics": {
                    "Stock P/E": "18.5",
                    "ROCE": "22.0%",
                    "ROE": "19.0%",
                    "Dividend Yield": "2.50%",
                }
            },
        },
    }


class TestFundamentalsLoader(unittest.TestCase):
    def test_load_and_highlights(self):
        with tempfile.TemporaryDirectory() as td:
            proj_root = Path(td)
            fund_dir = proj_root / "research" / "data" / "fundamentals"
            store = FundamentalsStore(fund_dir)
            store.save_symbol_payload(_sample_payload("DEMO"))
            store.rebuild_long_csvs()

            metrics = load_fundamentals_from_store("DEMO", root=proj_root)
            self.assertIsNotNone(metrics)
            assert metrics is not None
            self.assertEqual(metrics["_source"], "local")
            self.assertAlmostEqual(metrics["pe_ratio"], 18.5)
            self.assertAlmostEqual(metrics["revenue_growth"], 0.15, places=4)
            self.assertAlmostEqual(metrics["profit_growth"], 0.2, places=4)
            self.assertAlmostEqual(metrics["debt_to_equity"], 0.5, places=4)

            highlights = build_fundamentals_highlights(metrics, source="local")
            self.assertTrue(any("P/E 18.5" in h for h in highlights))
            self.assertTrue(any("Sales growth +15.0%" in h for h in highlights))

    def test_analyzer_uses_local_store(self):
        with tempfile.TemporaryDirectory() as td:
            fund_dir = Path(td) / "research" / "data" / "fundamentals"
            store = FundamentalsStore(fund_dir)
            store.save_symbol_payload(_sample_payload("DEMO"))

            class MockProvider:
                pass

            analyzer = FundamentalsAnalyzer(MockProvider())
            import analyzer.fundamentals_analyzer as fa

            original = fa.load_fundamentals_from_store

            def _load(sym, root=None):
                payload = store.load_symbol_payload(sym)
                if not payload:
                    return None
                from research.fundamentals_loader import _payload_to_fundamentals

                return _payload_to_fundamentals(payload)

            fa.load_fundamentals_from_store = _load
            try:
                bundle = analyzer.analyze_fundamentals_bundle("DEMO")
            finally:
                fa.load_fundamentals_from_store = original

            self.assertEqual(bundle["source"], "local")
            self.assertGreater(bundle["score"], 50)
            self.assertTrue(bundle["highlights"])


if __name__ == "__main__":
    unittest.main()
