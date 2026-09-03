"""
Unit tests for GS Quant borrow P1 — Canonical Market Data Service (OIE-001).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from contracts.market_data import CanonicalQuote, DataAuthority, QuotePurpose
from trading_app.market_data_service import MarketDataService, _quote_from_dict


class TestCanonicalQuote(unittest.TestCase):
    def test_execution_grade_requires_ws_live(self):
        q = CanonicalQuote(
            symbol="RELIANCE",
            exchange="NSE",
            ltp=2500.0,
            source="ANGEL_WEBSOCKET",
            data_authority=DataAuthority.ANGEL_WS_LIVE.value,
            purpose=QuotePurpose.EXECUTION.value,
            data_quality="VALID",
        )
        self.assertTrue(q.is_execution_grade)

    def test_rest_is_not_execution_grade(self):
        q = CanonicalQuote(
            symbol="RELIANCE",
            exchange="NSE",
            ltp=2500.0,
            source="ANGEL_REST",
            data_authority=DataAuthority.ANGEL_REST_REFERENCE.value,
            purpose=QuotePurpose.DISPLAY.value,
            data_quality="VALID",
        )
        self.assertFalse(q.is_execution_grade)


class TestMarketDataService(unittest.TestCase):
    def test_execution_uses_require_ltp_fail_closed(self):
        svc = MarketDataService()
        with patch("trading_app.market_data_service._bridge") as bridge_fn:
            bridge = bridge_fn.return_value
            bridge.require_ltp.return_value = (False, None, "WS stale")
            res = svc.resolve("RELIANCE", "NSE", QuotePurpose.EXECUTION)
            self.assertFalse(res.ok)
            self.assertFalse(res.paper_execution_allowed)
            self.assertIn("WS stale", res.error)
            bridge.require_ltp.assert_called_once()

    def test_execution_success_maps_canonical_quote(self):
        svc = MarketDataService()
        raw = {
            "ltp": 100.0,
            "source": "ANGEL_WEBSOCKET",
            "price_source": "ANGEL_WEBSOCKET",
            "data_authority": "ANGEL_WS_LIVE",
            "data_quality": "VALID",
            "age_sec": 1.2,
            "exchange": "NSE",
            "live": True,
        }
        with patch("trading_app.market_data_service._bridge") as bridge_fn:
            bridge = bridge_fn.return_value
            bridge.require_ltp.return_value = (True, raw, "")
            res = svc.resolve("INFY", "NSE", QuotePurpose.EXECUTION)
            self.assertTrue(res.ok)
            self.assertTrue(res.paper_execution_allowed)
            self.assertEqual(res.quote.ltp, 100.0)
            self.assertEqual(res.quote.purpose, QuotePurpose.EXECUTION.value)

    def test_display_allows_rest_reference(self):
        svc = MarketDataService()
        raw = {
            "ltp": 99.0,
            "source": "ANGEL_REST",
            "data_authority": "ANGEL_REST_REFERENCE",
            "change_pct": 0.5,
            "live": True,
        }
        with patch("trading_app.market_data_service._bridge") as bridge_fn:
            bridge = bridge_fn.return_value
            bridge.get_ltp_quote.return_value = raw
            bridge.resolve_data_authority.return_value = {
                "data_authority": "ANGEL_WS_DISCONNECTED",
                "paper_execution_allowed": False,
            }
            res = svc.resolve("INFY", "NSE", QuotePurpose.DISPLAY)
            self.assertTrue(res.ok)
            self.assertFalse(res.paper_execution_allowed)
            self.assertEqual(res.quote.data_authority, "ANGEL_REST_REFERENCE")

    def test_quote_from_dict_infers_ws_authority(self):
        q = _quote_from_dict(
            "NIFTY",
            "NSE",
            {"ltp": 25000.0, "source": "ANGEL_WEBSOCKET", "live": True},
            QuotePurpose.DISPLAY,
        )
        self.assertEqual(q.data_authority, DataAuthority.ANGEL_WS_LIVE.value)


class TestMarketDataFeedNoSynthetic(unittest.TestCase):
    def test_snapshot_fails_closed_when_angel_unavailable(self):
        from trading_app.market_data_feed import MarketDataFeedManager

        with patch("trading_app.market_data_service.get_market_data_service") as get_svc:
            svc = get_svc.return_value
            svc.get_index_inputs.return_value = {"ok": False, "source": "ANGEL_UNAVAILABLE"}
            svc.get_status.return_value = {
                "data_authority": "NO_VALID_MARKET_DATA",
                "last_tick_age_sec": None,
                "websocket_streaming": False,
            }
            snap = MarketDataFeedManager().get_latest_market_snapshot(allow_simulated_fallback=True)
            self.assertFalse(snap.data_quality_passed)
            self.assertEqual(snap.nifty_50.last_price, 0.0)
            self.assertNotEqual(snap.nifty_50.last_price, 24850.40)


if __name__ == "__main__":
    unittest.main()
