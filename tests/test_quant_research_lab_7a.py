"""Phase 7A continuation — adapters, robustness, certification persistence."""

from __future__ import annotations

import os
import tempfile
import unittest

from contracts.strategy_research import (
    BacktestMetricsSummary,
    ResearchHypothesis,
    ResearchSource,
    StrategyDefinitionDraft,
    StrategyLifecycleState,
)
from research.backtest_protocol import BacktestConstraints, BacktestCostModel, BacktestResult, NullBacktestEngine
from research.certification_store import CertificationStore
from research.legacy_backtest_adapter import LegacyBacktestAdapter
from research.robustness import MonteCarloEngine, WalkForwardEngine, build_walk_forward_windows
from research.strategy_certification_engine import StrategyCertificationEngine


class TestWalkForwardWindows(unittest.TestCase):
    def test_builds_multiple_folds(self):
        windows = build_walk_forward_windows(
            "2024-01-01", "2025-01-01", train_days=90, test_days=30, step_days=30
        )
        self.assertGreaterEqual(len(windows), 3)
        self.assertLess(windows[0].train_start, windows[0].test_start)


class TestMonteCarlo(unittest.TestCase):
    def test_shuffle_monte_carlo(self):
        base = BacktestResult(
            run_id="r1",
            engine_name="NULL",
            strategy_id="s",
            strategy_version="1",
            period_start="2024-01-01",
            period_end="2024-06-01",
            metrics=BacktestMetricsSummary(total_trades=5, total_return_pct=10.0),
            cost_model=BacktestCostModel(),
            constraints=BacktestConstraints(initial_capital=100000),
            trades=[{"pnl": 1000}, {"pnl": -400}, {"pnl": 800}, {"pnl": -200}, {"pnl": 500}],
        )
        draft = StrategyDefinitionDraft(
            strategy_id="s",
            version="1",
            name="S",
            hypothesis_id="H",
            family="TREND",
            entry_rules_summary="x",
            exit_rules_summary="y",
        )
        report = MonteCarloEngine().run(draft, base, n_simulations=100, seed=1)
        self.assertEqual(report.n_simulations, 100)
        self.assertTrue(report.p5_total_return_pct <= report.median_total_return_pct <= report.p95_total_return_pct)


class TestCertificationStore(unittest.TestCase):
    def test_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "certs.jsonl")
            store = CertificationStore(path)
            eng = StrategyCertificationEngine(store=store)
            eng.submit_hypothesis(
                ResearchHypothesis(
                    hypothesis_id="H9",
                    title="T",
                    summary="S",
                    source=ResearchSource.INTERNAL,
                )
            )
            draft = StrategyDefinitionDraft(
                strategy_id="str_persist",
                version="0.1.0",
                name="Persist",
                hypothesis_id="H9",
                family="FACTOR",
                entry_rules_summary="a",
                exit_rules_summary="b",
            )
            eng.register_draft(draft)
            result = NullBacktestEngine().run(draft, None)
            cert = eng.certify_from_backtest(draft, result)
            latest = store.latest_for("str_persist", "0.1.0")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["record"]["package_hash"], cert.package_hash)
            self.assertEqual(eng.get_state("str_persist", "0.1.0"), StrategyLifecycleState.CERTIFIED)


class TestLegacyAdapterParse(unittest.TestCase):
    def test_parse_market_data_dict(self):
        draft = StrategyDefinitionDraft(
            strategy_id="x",
            version="1",
            name="x",
            hypothesis_id="h",
            family="TREND",
            entry_rules_summary="e",
            exit_rules_summary="x",
        )
        symbols, start, end = LegacyBacktestAdapter._parse_market_data(
            {"symbols": ["reliance", "INFY.NS"], "start": "2024-02-01", "end": "2024-03-01"},
            draft,
        )
        self.assertEqual(symbols, ["RELIANCE", "INFY"])
        self.assertEqual(start, "2024-02-01")
        self.assertEqual(end, "2024-03-01")


class TestWalkForwardWithNullEngine(unittest.TestCase):
    def test_walk_forward_runs_folds(self):
        eng = WalkForwardEngine(NullBacktestEngine())
        draft = StrategyDefinitionDraft(
            strategy_id="wf",
            version="1",
            name="WF",
            hypothesis_id="h",
            family="TREND",
            entry_rules_summary="e",
            exit_rules_summary="x",
        )
        report = eng.run(
            draft,
            symbols=["RELIANCE"],
            start="2024-01-01",
            end="2024-12-01",
            train_days=60,
            test_days=30,
            step_days=30,
        )
        self.assertGreaterEqual(len(report.folds), 1)
        self.assertTrue(report.report_id.startswith("wf-"))


if __name__ == "__main__":
    unittest.main()
