"""ARASS certification package (VAL-E) — research only, never LIVE."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research.certification_store import CertificationStore
from research.certify_arass import build_arass_certification_package
from research.strategy_certification_engine import StrategyCertificationEngine


class TestCertifyArass(unittest.TestCase):
    def test_package_pending_not_live(self):
        root = Path(__file__).resolve().parents[1]
        result = root / "backtesting/results/arass_NIFTY_2024-01-01_2026-07-31.json"
        if not result.exists():
            self.skipTest("ARASS result JSON missing")

        with tempfile.TemporaryDirectory() as td:
            # Isolate store path
            store_path = Path(td) / "certs.jsonl"
            # Monkeypatch via building package then checking live flag in output
            package = build_arass_certification_package(result_path=result, status="AUTO")
            self.assertFalse(package["strategy"]["live_eligible"])
            self.assertFalse(package["strategy"]["paper_promoted"])
            self.assertFalse(package["promotion_bar_met"])
            self.assertEqual(package["certification"]["status"], "PENDING")
            self.assertTrue(package["certification"]["package_hash"])
            # Engine must not report live eligible for ARASS 1.0.0
            eng = StrategyCertificationEngine(store=CertificationStore(str(store_path)))
            self.assertFalse(eng.is_live_eligible("ARASS", "1.0.0"))


if __name__ == "__main__":
    unittest.main()
