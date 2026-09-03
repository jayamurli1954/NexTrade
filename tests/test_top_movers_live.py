"""Top movers must be market-wide NSE (or watchlist fallback) — never fixed lists."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from web_dashboard import UnifiedWebAppHandler


class TestTopMoversMarketWide(unittest.TestCase):
    def test_uses_nse_market_movers_not_fixed_symbols(self):
        handler = UnifiedWebAppHandler.__new__(UnifiedWebAppHandler)
        fake_nse = {
            "ok": True,
            "gainers": [
                {"symbol": "COFORGE", "ltp": 1686.0, "change_pct": 10.31},
                {"symbol": "AFFLE", "ltp": 1631.8, "change_pct": 9.31},
            ],
            "losers": [
                {"symbol": "SUZLON", "ltp": 48.02, "change_pct": -9.65},
                {"symbol": "VBL", "ltp": 430.0, "change_pct": -7.43},
            ],
            "category": "allSec",
            "source": "NSE_LIVE_ANALYSIS",
        }
        with patch("trading_app.nse_market_movers.fetch_nse_equity_movers", return_value=fake_nse):
            with patch("web_dashboard._fetch_nse_ltp_map", return_value={}):
                movers = handler._compute_top_movers(limit=2)
        self.assertEqual([g["symbol"] for g in movers["gainers"]], ["COFORGE", "AFFLE"])
        self.assertEqual([l["symbol"] for l in movers["losers"]], ["SUZLON", "VBL"])
        self.assertEqual(movers["source"], "NSE_MARKET")
        self.assertNotIn("RELIANCE", [g["symbol"] for g in movers["gainers"]])
        self.assertNotIn("TITAN", [l["symbol"] for l in movers["losers"]])

    def test_watchlist_fallback_when_nse_down(self):
        handler = UnifiedWebAppHandler.__new__(UnifiedWebAppHandler)
        with patch(
            "trading_app.nse_market_movers.fetch_nse_equity_movers",
            return_value={"ok": False, "gainers": [], "losers": [], "error": "down"},
        ):
            with patch.object(handler, "_load_watchlist_file", return_value=["AAA", "BBB"]):
                with patch("web_dashboard._fetch_nse_ltp_map") as fetch:
                    fetch.return_value = {
                        "AAA": {"ltp": 100.0, "change_pct": 2.0, "has_prev_close": True, "source": "ANGEL_WEBSOCKET"},
                        "BBB": {"ltp": 200.0, "change_pct": -3.0, "has_prev_close": True, "source": "ANGEL_WEBSOCKET"},
                    }
                    movers = handler._compute_top_movers(limit=2)
        self.assertEqual(movers["source"], "ANGEL_WATCHLIST_FALLBACK")
        self.assertEqual(movers["gainers"][0]["symbol"], "AAA")
        self.assertEqual(movers["losers"][0]["symbol"], "BBB")


class TestNseNormalizer(unittest.TestCase):
    def test_normalize_filters_sign(self):
        from trading_app.nse_market_movers import _normalize_rows

        rows = [
            {"symbol": "COFORGE", "ltp": 1686, "net_price": 10.31},
            {"symbol": "BAD", "ltp": 100, "net_price": -1.0},
        ]
        gainers = _normalize_rows(rows, want_positive=True)
        self.assertEqual([r["symbol"] for r in gainers], ["COFORGE"])


if __name__ == "__main__":
    unittest.main()
