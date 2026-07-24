# tests/test_risk_concurrency.py
"""
High-Concurrency & 1:1 Decision-Audit Correspondence Stress Test Suite (Sub-Phase 2H-5).
Tests 100 concurrent threads evaluating RiskEngine requests and logging audit decisions
to verify zero lost events, zero sequence skips, zero duplicate IDs, and 1:1 decision-audit correspondence.
"""
import os
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from contracts.signal import Signal, SignalAction
from contracts.order import OrderSide
from contracts.funds import FundsInfo
from contracts.risk import (
    RiskContext,
    RiskLimits,
    OrderIntent,
    RiskDecision,
    RiskDecisionStatus,
)
from risk.position_sizer import PositionSizer
from risk.risk_limits import PortfolioRiskEvaluator
from risk.kill_switch import KillSwitchManager
from risk.risk_engine import RiskEngine
from risk.audit_logger import RiskAuditLogger


class TestRiskConcurrency(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.jsonl_path = os.path.join(self.temp_dir, "risk_decisions.jsonl")
        self.csv_path = os.path.join(self.temp_dir, "risk_decisions.csv")
        self.state_file = os.path.join(self.temp_dir, "kill_switch_state.json")

        self.kill_switch = KillSwitchManager(state_file_path=self.state_file)
        self.sizer = PositionSizer()
        self.portfolio_evaluator = PortfolioRiskEvaluator()
        self.audit_logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)

        self.engine = RiskEngine(
            sizer=self.sizer,
            portfolio_evaluator=self.portfolio_evaluator,
            kill_switch_manager=self.kill_switch
        )

        self.now = datetime.now(timezone.utc)
        self.funds = FundsInfo(
            available_cash=100000.0,
            used_margin=0.0,
            available_margin=100000.0,
            total_equity=100000.0
        )
        self.context = RiskContext(funds=self.funds)
        self.limits = RiskLimits()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_100_thread_concurrency_stress_and_1to1_correspondence(self):
        """Execute 100 concurrent threads evaluating risk and logging audit events."""
        logged_events = []
        lock = threading.Lock()

        def worker(thread_idx):
            sig = Signal(
                signal_id=f"SIG-CONC-{thread_idx}",
                strategy_id=f"STRAT_{thread_idx % 5}",
                symbol="RELIANCE",
                exchange="NSE",
                action=SignalAction.BUY,
                entry_price=2500.0,
                stop_loss=2450.0,
                target_price=2600.0,
                confidence=0.85,
                timestamp=self.now,
                expiry=self.now,
                source="StressTest"
            )

            dec = self.engine.evaluate_order_request(
                signal=sig,
                order_side=OrderSide.BUY,
                order_intent=OrderIntent.ENTRY,
                requested_quantity=8,
                context=self.context,
                limits=self.limits
            )

            event = self.audit_logger.log_decision(
                decision=dec,
                symbol="RELIANCE",
                exchange="NSE",
                strategy_id=sig.strategy_id
            )

            with lock:
                logged_events.append((dec, event))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 1. Total event count check
        self.assertEqual(len(logged_events), 100)

        # 2. 1:1 Correspondence & Uniqueness checks
        decision_ids = set()
        audit_event_ids = set()
        sequence_numbers = set()

        for dec, event in logged_events:
            self.assertEqual(dec.decision_id, event.decision_id)
            self.assertEqual(dec.signal_id, event.signal_id)
            self.assertEqual(dec.approved_quantity, event.approved_quantity)

            decision_ids.add(dec.decision_id)
            audit_event_ids.add(event.audit_event_id)
            sequence_numbers.add(event.sequence_number)

        self.assertEqual(len(decision_ids), 100)
        self.assertEqual(len(audit_event_ids), 100)
        self.assertEqual(sequence_numbers, set(range(1, 101)))

        # 3. Cryptographic hash chain continuity check across all 100 events
        res = self.audit_logger.verify_integrity()
        self.assertTrue(res.is_valid)
        self.assertEqual(res.total_records_checked, 100)


if __name__ == "__main__":
    unittest.main()
