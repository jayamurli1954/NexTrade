"""Watchlist add/remove persist to watchlist.json (web dashboard API helpers)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_dashboard import (
    add_watchlist_symbol,
    build_watchlist_csv,
    load_watchlist_symbols,
    remove_watchlist_symbol,
    _normalize_watchlist_symbol,
)


class TestWatchlistSymbolNormalize(unittest.TestCase):
    def test_bare_and_eq_suffix(self):
        self.assertEqual(_normalize_watchlist_symbol("sbin")[0], "SBIN")
        self.assertEqual(_normalize_watchlist_symbol("SBIN-EQ")[0], "SBIN")
        self.assertEqual(_normalize_watchlist_symbol("M&M")[0], "M&M")

    def test_rejects_empty_and_company_name(self):
        self.assertTrue(_normalize_watchlist_symbol("")[1])
        self.assertTrue(_normalize_watchlist_symbol("State Bank of India")[1])


class TestWatchlistPersist(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(["RELIANCE", "INFY"], f)

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def test_add_then_reload(self):
        res = add_watchlist_symbol("COFORGE", path=self.path)
        self.assertTrue(res["success"], res)
        self.assertEqual(res["symbol"], "COFORGE")
        self.assertEqual(load_watchlist_symbols(self.path), ["COFORGE", "INFY", "RELIANCE"])

    def test_duplicate_rejected(self):
        res = add_watchlist_symbol("reliance", path=self.path)
        self.assertFalse(res["success"])
        self.assertIn("already", res["error"].lower())
        self.assertEqual(load_watchlist_symbols(self.path), ["INFY", "RELIANCE"])

    def test_remove(self):
        res = remove_watchlist_symbol("INFY", path=self.path)
        self.assertTrue(res["success"], res)
        self.assertEqual(load_watchlist_symbols(self.path), ["RELIANCE"])

    def test_load_is_alphabetical(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(["WIPRO", "ABB", "TCS"], f)
        self.assertEqual(load_watchlist_symbols(self.path), ["ABB", "TCS", "WIPRO"])


class TestWatchlistCsv(unittest.TestCase):
    def test_csv_includes_header_and_row(self):
        raw = build_watchlist_csv([
            {
                "symbol": "SBIN",
                "ltp": "₹800.00",
                "change": "+₹2.00",
                "change_pct": "+0.25%",
                "volume": "1,000",
                "price_source": "ANGEL",
            }
        ])
        text = raw.decode("utf-8-sig")
        self.assertIn("Symbol,LTP,Change,Change %,Volume,Price Source", text)
        self.assertIn("SBIN", text)
        self.assertIn("ANGEL", text)

    def test_csv_rows_sorted_by_symbol(self):
        raw = build_watchlist_csv([
            {"symbol": "WIPRO", "ltp": "1", "change": "", "change_pct": "", "volume": "", "price_source": ""},
            {"symbol": "ABB", "ltp": "2", "change": "", "change_pct": "", "volume": "", "price_source": ""},
        ])
        lines = raw.decode("utf-8-sig").strip().splitlines()
        self.assertTrue(lines[1].startswith("ABB"))
        self.assertTrue(lines[2].startswith("WIPRO"))


if __name__ == "__main__":
    unittest.main()
