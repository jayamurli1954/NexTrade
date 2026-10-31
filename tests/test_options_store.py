"""Tests for options store + excel loader helpers (no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.arass.definition import ArassParams
from research.arass.engine import ArassBacktestEngine
from research.arass.options_store import OptionsStore, normalize_options_df


class TestOptionsStore(unittest.TestCase):
    def test_normalize_and_lookup(self):
        raw = pd.DataFrame(
            [
                {
                    "DATE": "2026-07-24",
                    "EXPIRY": "2026-07-28",
                    "OPTION TYPE": "CE",
                    "STRIKE PRICE": 24500,
                    "OPEN": 3.7,
                    "HIGH": 5.65,
                    "LOW": 3.0,
                    "CLOSE": 3.9,
                    "SYMBOL": "NIFTY",
                },
                {
                    "DATE": "2026-07-24",
                    "EXPIRY": "2026-07-28",
                    "OPTION TYPE": "PE",
                    "STRIKE PRICE": 24500,
                    "OPEN": 810,
                    "HIGH": 865,
                    "LOW": 652,
                    "CLOSE": 704.8,
                    "SYMBOL": "NIFTY",
                },
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "opts.csv"
            store = OptionsStore.empty(path)
            store.merge(raw)
            store.save()
            loaded = OptionsStore.load(path)
            hit = loaded.straddle(
                symbol="NIFTY",
                asof=pd.Timestamp("2026-07-24"),
                expiry=pd.Timestamp("2026-07-28"),
                strike=24500,
                field="close",
            )
            self.assertIsNotNone(hit)
            self.assertAlmostEqual(hit[0], 3.9)
            self.assertAlmostEqual(hit[1], 704.8)
            hi = loaded.lookup(
                symbol="NIFTY",
                asof=pd.Timestamp("2026-07-24"),
                expiry=pd.Timestamp("2026-07-28"),
                strike=24500,
                option_type="CE",
                field="high",
            )
            self.assertAlmostEqual(hi, 5.65)

    def test_engine_uses_options_store(self):
        store = OptionsStore.empty(Path("unused.csv"))
        store.merge(
            pd.DataFrame(
                [
                    {
                        "date": "2024-01-03",
                        "expiry": "2024-01-04",
                        "strike": 22000,
                        "option_type": "CE",
                        "open": 80,
                        "high": 100,
                        "low": 70,
                        "close": 90,
                        "symbol": "NIFTY",
                    },
                    {
                        "date": "2024-01-03",
                        "expiry": "2024-01-04",
                        "strike": 22000,
                        "option_type": "PE",
                        "open": 80,
                        "high": 110,
                        "low": 60,
                        "close": 85,
                        "symbol": "NIFTY",
                    },
                ]
            )
        )
        engine = ArassBacktestEngine(
            params=ArassParams(use_synthetic_premiums=False),
            options_store=store,
        )
        ce, pe = engine._mark_premiums(
            22000,
            {"expiry": "2024-01-04", "strike": 22000, "symbol": "NIFTY"},
            pd.Timestamp("2024-01-03 10:35"),
            0.14,
            field="close",
        )
        self.assertEqual(ce, 90)
        self.assertEqual(pe, 85)
        self.assertEqual(engine._options_hits, 1)


class TestNormalizeJugaadSample(unittest.TestCase):
    def test_sample_csv_if_present(self):
        sample = Path("research/data/options_sample/NIFTY_2026-07-28_24500_CE.csv")
        if not sample.exists():
            self.skipTest("sample CE csv not present")
        df = normalize_options_df(pd.read_csv(sample))
        self.assertIn("close", df.columns)
        self.assertTrue((df["option_type"] == "CE").all())


if __name__ == "__main__":
    unittest.main()
