"""FI-2: Fundamental Service + opportunity display (gates unchanged)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from research.fundamental_service import (
    FundamentalService,
    badge_for_score,
    build_ai_summary,
)
from trading_app.opportunity_engine import OpportunityEngine


class TestFi2FundamentalService(unittest.TestCase):
    def test_badge_bands(self):
        self.assertEqual(badge_for_score(90), "Excellent")
        self.assertEqual(badge_for_score(70), "Good")
        self.assertEqual(badge_for_score(55), "Fair")
        self.assertEqual(badge_for_score(40), "Weak")
        self.assertEqual(badge_for_score(10), "Poor")

    def test_ai_summary_rule_based(self):
        text = build_ai_summary(
            direction="BUY",
            why_technical=["RSI oversold (32)", "Volume ratio 1.80x vs average"],
            factor_scores={"quality": 88, "value": 70, "financial_health": 90, "growth": 40, "overall_fundamental": 75},
        )
        self.assertIn("Technicals suggest", text)
        self.assertIn("Fundamentals indicate", text)
        self.assertNotIn("LLM", text)

    def test_service_loads_tcs_from_store(self):
        svc = FundamentalService()
        intel = svc.get_symbol_intelligence("TCS")
        if intel is None:
            self.skipTest("factor store not built")
        self.assertEqual(intel["source"], "factor_store")
        self.assertIn("factor_version", intel)
        self.assertTrue(str(intel.get("as_of_label") or "").startswith("As of FY"))
        self.assertIsNotNone(intel["factor_scores"].get("overall_fundamental"))
        self.assertIn(intel["factor_badges"]["quality"], {"Excellent", "Good", "Fair", "Weak", "Poor", "N/A"})


class TestFi2OpportunityFreeze(unittest.TestCase):
    def _signal(self, conf=0.72):
        return {
            "symbol": "TCS",
            "action": "BUY",
            "confidence": conf,
            "reason": "Near Golden Ratio (61.8%) + RSI oversold (32.1)",
            "current_price": 3500.0,
            "stop_loss": 3400.0,
            "target": 3700.0,
            "rsi": 32.1,
            "volume_ratio": 1.8,
        }

    def test_confidence_unchanged_with_factors(self):
        eng = OpportunityEngine()
        sig = self._signal(0.72)
        live = {"TCS": {"ltp": 3500.0, "source": "ANGEL"}}
        opps = eng.signals_to_opportunities(signals=[sig], live_ltp_map=live, top_n=5, min_confidence=0.55)
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0].signal_strength_pct, 72.0)
        # Technical why should not contain PE/ROCE raw factor lines as primary
        why_blob = " ".join(opps[0].why_this_trade).lower()
        self.assertIn("rsi", why_blob)
        # Factors attached for display
        if opps[0].factor_scores:
            self.assertIsNotNone(opps[0].opportunity_strength)
            self.assertEqual(opps[0].opportunity_strength["technical"], 72.0)
            self.assertIn("Display only", opps[0].opportunity_strength.get("note", ""))
            self.assertTrue(opps[0].ai_summary)

    def test_ranking_order_unchanged(self):
        eng = OpportunityEngine()
        signals = [
            {**self._signal(0.90), "symbol": "AAA"},
            {**self._signal(0.80), "symbol": "BBB"},
            {**self._signal(0.70), "symbol": "CCC"},
        ]
        live = {s: {"ltp": 100.0, "source": "ANGEL"} for s in ("AAA", "BBB", "CCC")}
        # Patch intelligence so all have factors (should not reorder)
        fake = {
            "investment_thesis": ["Strong quality (90/100)"],
            "factor_scores": {"overall_fundamental": 50},
            "factor_badges": {},
            "factor_trends": {},
            "valuation_relatives": {},
            "factor_version": "1.1",
            "generated_at": "x",
            "fiscal_year": 2026,
            "as_of_label": "As of FY 2026",
        }
        with patch("research.fundamental_service.get_fundamental_service") as m:
            inst = m.return_value
            inst.get_symbol_intelligence.return_value = fake
            opps = eng.signals_to_opportunities(signals=signals, live_ltp_map=live, top_n=10, min_confidence=0.55)
        self.assertEqual([o.symbol for o in opps], ["AAA", "BBB", "CCC"])
        self.assertEqual([o.signal_strength_pct for o in opps], [90.0, 80.0, 70.0])


if __name__ == "__main__":
    unittest.main()
