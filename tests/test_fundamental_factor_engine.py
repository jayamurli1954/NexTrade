"""Tests for Fundamental Factor Engine FI-1 (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.factor_score_store import FactorScoreStore
from research.fundamental_factor_engine import (
    compute_factors_for_payload,
    load_factor_config,
)
from research.fundamentals_store import FundamentalsStore


def _payload_stable(symbol: str = "STABLE") -> dict:
    years = [f"Mar {y}" for y in range(2020, 2026)]
    sales = [100 + i * 8 for i in range(len(years))]
    pat = [12 + i for i in range(len(years))]
    roce = [17 + i * 0.5 for i in range(len(years))]
    roe = [15 + i * 0.4 for i in range(len(years))]
    return {
        "symbol": symbol,
        "scraped_at": "2026-01-01T00:00:00+00:00",
        "sections": {
            "profit_loss": {
                "table": {
                    "headers": years,
                    "rows": [
                        {"label": "Sales", "values": sales},
                        {"label": "Net Profit", "values": pat},
                    ],
                }
            },
            "balance_sheet": {
                "headers": years,
                "rows": [
                    {"label": "Borrowings", "values": [40] * len(years)},
                    {"label": "Equity Capital", "values": [50] * len(years)},
                    {"label": "Reserves", "values": [200 + i * 10 for i in range(len(years))]},
                ],
            },
            "cash_flow": {
                "headers": years,
                "rows": [{"label": "Cash from Operating Activity", "values": [v * 1.1 for v in pat]}],
            },
            "ratios": {
                "headers": years,
                "rows": [
                    {"label": "ROCE %", "values": roce},
                    {"label": "ROE %", "values": roe},
                ],
            },
            "shareholding": {
                "headers": ["Mar 2025"],
                "rows": [{"label": "Promoters", "values": [55.0]}],
            },
            "pros_cons": {
                "pros": ["Consistent compounder"],
                "cons": [],
                "key_metrics": {
                    "Stock P/E": "18.0",
                    "ROCE": "19.5%",
                    "ROE": "17.0%",
                    "Dividend Yield": "1.50%",
                },
            },
            "peer_comparison": {
                "sector": "Consumer",
                "industry": "FMCG",
                "peers": [
                    {"name": "Stable Co", "values": {"P/E": 18.0, "ROCE %": 19.5}},
                    {"name": "Peer A", "values": {"P/E": 28.0, "ROCE %": 14.0}},
                    {"name": "Peer B", "values": {"P/E": 30.0, "ROCE %": 12.0}},
                    {"name": "Peer C", "values": {"P/E": 32.0, "ROCE %": 11.0}},
                ],
            },
        },
    }


def _payload_volatile(symbol: str = "VOLATILE") -> dict:
    years = [f"Mar {y}" for y in range(2020, 2026)]
    return {
        "symbol": symbol,
        "scraped_at": "2026-01-01T00:00:00+00:00",
        "sections": {
            "profit_loss": {
                "table": {
                    "headers": years,
                    "rows": [
                        {"label": "Sales", "values": [100, 70, 140, 60, 160, 80]},
                        {"label": "Net Profit", "values": [25, 2, 30, -5, 28, 3]},
                    ],
                }
            },
            "balance_sheet": {
                "headers": years,
                "rows": [
                    {"label": "Borrowings", "values": [300] * 6},
                    {"label": "Equity Capital", "values": [50] * 6},
                    {"label": "Reserves", "values": [50] * 6},
                ],
            },
            "cash_flow": {
                "headers": years,
                "rows": [{"label": "Cash from Operating Activity", "values": [1, 1, 1, 1, 1, 1]}],
            },
            "ratios": {
                "headers": years,
                "rows": [
                    {"label": "ROCE %", "values": [25, 5, 30, 4, 28, 6]},
                    {"label": "ROE %", "values": [22, 3, 27, 2, 24, 5]},
                ],
            },
            "pros_cons": {"key_metrics": {"Stock P/E": "45.0", "ROCE": "6%", "ROE": "5%"}},
            "peer_comparison": {"sector": "Industrial", "industry": "Conglomerates", "peers": []},
        },
    }


class TestFundamentalFactorEngine(unittest.TestCase):
    def test_stable_scores_and_peers(self):
        fs = compute_factors_for_payload(_payload_stable(), mode="current")
        self.assertEqual(fs.symbol, "STABLE")
        self.assertIsNotNone(fs.overall_fundamental)
        self.assertGreater(fs.quality or 0, 50)
        self.assertGreater(fs.consistency or 0, 50)
        self.assertIsNotNone(fs.relatives.get("sector_pe_median"))
        self.assertLess(fs.relatives.get("pe_vs_sector_pct"), 0)
        self.assertTrue(any("sector P/E" in t for t in fs.thesis))

    def test_consistency_penalizes_volatility(self):
        stable = compute_factors_for_payload(_payload_stable(), mode="current")
        volatile = compute_factors_for_payload(_payload_volatile(), mode="current")
        self.assertIsNotNone(stable.consistency)
        self.assertIsNotNone(volatile.consistency)
        self.assertGreater(stable.consistency, volatile.consistency)

    def test_historical_no_peer_lookahead(self):
        fs = compute_factors_for_payload(_payload_stable(), mode="historical", fiscal_year=2022)
        self.assertEqual(fs.fiscal_year, 2022)
        self.assertEqual(fs.mode, "historical")
        self.assertIsNone(fs.relatives.get("sector_pe_median"))
        self.assertEqual(fs.relatives.get("note"), "historical_snapshot_no_peer_table")

    def test_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = FundamentalsStore(root / "research" / "data" / "fundamentals")
            # FundamentalsStore expects root = fundamentals dir
            fund_root = root
            raw = FundamentalsStore(fund_root)
            raw.save_symbol_payload(_payload_stable("STABLE"))

            from research.fundamental_factor_engine import compute_all_current, scores_to_symbol_record
            from research.factor_score_store import FactorScoreStore, utc_now_iso

            store = FactorScoreStore(fund_root)
            current = compute_all_current(raw)
            payload = {
                "built_at": utc_now_iso(),
                "symbols": {s: scores_to_symbol_record(fs) for s, fs in current.items()},
            }
            store.save_current(payload)
            loaded = store.load_current_symbol("STABLE")
            self.assertIsNotNone(loaded)
            self.assertIn("overall_fundamental", loaded["scores"])

    def test_config_loads(self):
        cfg = load_factor_config()
        self.assertIn("overall_weights", cfg)
        self.assertAlmostEqual(sum(cfg["overall_weights"].values()), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
