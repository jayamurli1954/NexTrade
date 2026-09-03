"""Phase 7A — Strategy Certification Invariant & research lifecycle tests."""

from __future__ import annotations

import unittest

from contracts.strategy_research import (
    STRATEGY_CATALOGUE_FAMILIES,
    ResearchHypothesis,
    ResearchSource,
    StrategyDefinitionDraft,
    StrategyLifecycleError,
    StrategyLifecycleState,
    can_transition,
)
from research.backtest_protocol import NullBacktestEngine
from research.strategy_certification_engine import StrategyCertificationEngine


class TestStrategyLifecycleInvariant(unittest.TestCase):
    def test_live_eligible_requires_certification(self):
        self.assertFalse(
            can_transition(
                StrategyLifecycleState.PAPER,
                StrategyLifecycleState.LIVE_ELIGIBLE,
                has_valid_certification=False,
            )
        )
        self.assertTrue(
            can_transition(
                StrategyLifecycleState.PAPER,
                StrategyLifecycleState.LIVE_ELIGIBLE,
                has_valid_certification=True,
            )
        )

    def test_engine_blocks_live_without_cert(self):
        eng = StrategyCertificationEngine()
        hyp = ResearchHypothesis(
            hypothesis_id="H1",
            title="Momentum works in trending regimes",
            summary="Test hypothesis",
            source=ResearchSource.AWESOME_SYSTEMATIC_TRADING,
        )
        eng.submit_hypothesis(hyp)
        draft = StrategyDefinitionDraft(
            strategy_id="str_research_demo",
            version="0.1.0",
            name="Research Demo",
            hypothesis_id="H1",
            family="TREND_FOLLOWING",
            entry_rules_summary="Price > EMA",
            exit_rules_summary="Price < EMA",
        )
        eng.register_draft(draft)
        # Manually place at PAPER without a certification package
        eng._states[eng._key("str_research_demo", "0.1.0")] = StrategyLifecycleState.PAPER
        with self.assertRaises(StrategyLifecycleError):
            eng.transition("str_research_demo", "0.1.0", StrategyLifecycleState.LIVE_ELIGIBLE)

    def test_certify_then_live_eligible(self):
        eng = StrategyCertificationEngine()
        eng.submit_hypothesis(
            ResearchHypothesis(
                hypothesis_id="H2",
                title="Mean reversion in range",
                summary="Test",
                source=ResearchSource.INVESTMITRA,
            )
        )
        draft = StrategyDefinitionDraft(
            strategy_id="str_mr_demo",
            version="0.1.0",
            name="MR Demo",
            hypothesis_id="H2",
            family="MEAN_REVERSION",
            entry_rules_summary="RSI < 30",
            exit_rules_summary="RSI > 50",
        )
        eng.register_draft(draft)
        result = NullBacktestEngine().run(draft, market_data=None)
        cert = eng.certify_from_backtest(draft, result)
        self.assertTrue(cert.package_hash)
        self.assertEqual(eng.get_state("str_mr_demo", "0.1.0"), StrategyLifecycleState.CERTIFIED)
        eng.transition("str_mr_demo", "0.1.0", StrategyLifecycleState.PAPER)
        eng.transition("str_mr_demo", "0.1.0", StrategyLifecycleState.LIVE_ELIGIBLE)
        self.assertTrue(eng.is_live_eligible("str_mr_demo", "0.1.0"))

    def test_catalogue_taxonomy_present(self):
        self.assertIn("TREND_FOLLOWING", STRATEGY_CATALOGUE_FAMILIES)
        self.assertIn("MEAN_REVERSION", STRATEGY_CATALOGUE_FAMILIES)
        self.assertGreaterEqual(len(STRATEGY_CATALOGUE_FAMILIES), 5)


if __name__ == "__main__":
    unittest.main()
