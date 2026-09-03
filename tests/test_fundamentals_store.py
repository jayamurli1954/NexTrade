"""Tests for fundamentals store flattening (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.fundamentals_store import (
    FundamentalsStore,
    financial_table_to_long_rows,
    payload_to_long_frames,
)
from research.nse_xbrl_adapter import xbrl_filings_to_long_rows


class TestFundamentalsStore(unittest.TestCase):
    def test_financial_table_to_long(self):
        table = {
            "section": "Profit & Loss",
            "unit": "Rs. Crores",
            "currency": "INR",
            "period_type": "annual",
            "headers": ["Mar 2024", "Mar 2025"],
            "rows": [{"label": "Sales", "values": [100.0, 120.0], "unit": None, "is_subtotal": False}],
        }
        rows = financial_table_to_long_rows(symbol="RELIANCE", view="consolidated", section="profit_loss", table=table)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["metric"], "Sales")
        self.assertEqual(rows[0]["value"], 100.0)

    def test_rebuild_long_csvs(self):
        payload = {
            "symbol": "TCS",
            "view": "consolidated",
            "scraped_at": "2026-01-01T00:00:00+00:00",
            "sections": {
                "quarterly_results": {
                    "section": "Quarterly Results",
                    "unit": "Rs. Crores",
                    "currency": "INR",
                    "period_type": "quarterly",
                    "headers": ["Jun 2025"],
                    "rows": [{"label": "Sales", "values": [50.0], "unit": None, "is_subtotal": False}],
                },
                "profit_loss": {
                    "table": {
                        "section": "Profit & Loss",
                        "unit": "Rs. Crores",
                        "currency": "INR",
                        "period_type": "annual",
                        "headers": ["Mar 2025"],
                        "rows": [{"label": "Net Profit", "values": [10.0], "unit": None, "is_subtotal": False}],
                    },
                    "growth_tables": [],
                },
                "balance_sheet": None,
                "cash_flow": None,
                "ratios": {
                    "section": "Ratios",
                    "unit": "%",
                    "currency": "INR",
                    "period_type": "annual",
                    "headers": ["Mar 2025"],
                    "rows": [{"label": "ROCE", "values": [35.0], "unit": "%", "is_subtotal": False}],
                },
                "shareholding": None,
                "pros_cons": {"key_metrics": {"Market Cap": "12L Cr.", "P/E": 25.0}},
            },
        }
        frames = payload_to_long_frames(payload)
        self.assertEqual(len(frames["quarterly_pnl"]), 1)
        self.assertEqual(len(frames["pnl_annual"]), 1)
        self.assertEqual(len(frames["ratios_annual"]), 1)

        with tempfile.TemporaryDirectory() as td:
            store = FundamentalsStore(Path(td))
            store.save_symbol_payload(payload)
            counts = store.rebuild_long_csvs()
            self.assertEqual(counts["quarterly_pnl"], 1)
            self.assertTrue((store.long_dir / "pnl_annual.csv").exists())
            manifest = json.loads((store.root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["symbol_count"], 1)

    def test_xbrl_long_rows(self):
        filings = [
            {
                "symbol": "RELIANCE",
                "company_name": "Reliance Industries Limited",
                "seq_id": "1",
                "is_consolidated": True,
                "period_end": "2025-03-31",
                "q_revenue": 2.5e11,
                "q_pat": 3.0e10,
                "bs_total_assets": 1.8e12,
            }
        ]
        rows = xbrl_filings_to_long_rows("RELIANCE", filings)
        self.assertTrue(any(r["metric"] == "q_revenue" for r in rows))
        self.assertTrue(any(r["section"] == "balance_sheet" for r in rows))


if __name__ == "__main__":
    unittest.main()
