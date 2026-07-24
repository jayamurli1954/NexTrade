# tests/test_paper_adapter.py
"""
Unit Test Suite for NexTrade PaperBrokerAdapter (Sub-Phase 3C).
Verifies BrokerInterface protocol compliance, quantity preservation, paper isolation,
distinction between pre-submission REJECTED vs post-submission UNKNOWN (Invariant E14 & E15),
and full execution traceability (Invariant E16).
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from contracts.broker import BrokerInterface
from contracts.order import OrderSide, OrderType
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from brokers.paper_adapter import PaperBrokerAdapter
from order_manager.paper_trader import PaperTrader


class TestPaperBrokerAdapter(unittest.TestCase):

    def setUp(self):
        self.paper_trader = PaperTrader()
        self.adapter = PaperBrokerAdapter(paper_trader=self.paper_trader)
        self.now = datetime.now(timezone.utc)

    def test_protocol_compliance_and_no_live_broker_dependency(self):
        """Invariant E13: PaperBrokerAdapter implements BrokerInterface without live broker dependencies."""
        self.assertIsInstance(self.adapter, BrokerInterface)
        funds = self.adapter.get_account_funds()
        self.assertTrue(funds.available_cash > 0)
        self.assertEqual(len(self.adapter.get_positions()), 0)

    def test_valid_buy_execution_success(self):
        req = ExecutionRequest(
            execution_request_id="EXREQ-PA-01",
            idempotency_key="IDEM-PA-01",
            risk_decision_id="RD-PA-01",
            signal_id="SIG-PA-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            limit_price=2500.0,
            timestamp=self.now
        )
        res = self.adapter.execute_order(req)

        self.assertEqual(res.status, ExecutionStatus.FILLED)
        self.assertEqual(res.filled_quantity, 50)
        self.assertEqual(res.remaining_quantity, 0)
        self.assertEqual(res.execution_request_id, "EXREQ-PA-01")
        self.assertEqual(res.risk_decision_id, "RD-PA-01")
        self.assertTrue(res.broker_order_id.startswith("T202"))

    def test_quantity_preservation(self):
        """Invariant E12: Q_filled <= Q_execution <= Q_approved."""
        req = ExecutionRequest(
            execution_request_id="EXREQ-PA-02",
            idempotency_key="IDEM-PA-02",
            risk_decision_id="RD-PA-02",
            symbol="INFY",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=30,
            execution_quantity=30,
            limit_price=1600.0,
            timestamp=self.now
        )
        res = self.adapter.execute_order(req)
        self.assertTrue(0 <= res.filled_quantity <= req.execution_quantity <= req.approved_quantity)

    def test_pre_submission_exception_isolation_returns_rejected(self):
        """Invariant E15: Pre-submission adapter exception returns controlled ExecutionResult(status=REJECTED)."""
        mock_pt = MagicMock()
        mock_pt.execute_order.side_effect = ValueError("Invalid symbol parameter in paper simulator")

        err_adapter = PaperBrokerAdapter(paper_trader=mock_pt)
        req = ExecutionRequest(
            execution_request_id="EXREQ-PA-03",
            idempotency_key="IDEM-PA-03",
            risk_decision_id="RD-PA-03",
            symbol="BADSYM",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=10,
            approved_quantity=10,
            execution_quantity=10,
            timestamp=self.now
        )
        res = err_adapter.execute_order(req)

        self.assertEqual(res.status, ExecutionStatus.REJECTED)
        self.assertFalse(res.requires_reconciliation)
        self.assertIn("DETERMINISTIC_BROKER_ERROR", res.rejection_reason)

    def test_unknown_after_submission_boundary_returns_unknown(self):
        """Invariant E14: Post-submission TimeoutError returns status UNKNOWN with requires_reconciliation = True."""
        mock_pt = MagicMock()
        mock_pt.execute_order.side_effect = TimeoutError("Network socket read timeout on submission response")

        timeout_adapter = PaperBrokerAdapter(paper_trader=mock_pt)
        req = ExecutionRequest(
            execution_request_id="EXREQ-PA-04",
            idempotency_key="IDEM-PA-04",
            risk_decision_id="RD-PA-04",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=50,
            approved_quantity=20,
            execution_quantity=20,
            timestamp=self.now
        )
        res = timeout_adapter.execute_order(req)

        self.assertEqual(res.status, ExecutionStatus.UNKNOWN)
        self.assertTrue(res.requires_reconciliation)
        self.assertIn("POST_SUBMISSION_TIMEOUT", res.rejection_reason)


    def test_traceability_preservation(self):
        """Invariant E16: Full execution lineage preserved in ExecutionResult."""
        req = ExecutionRequest(
            execution_request_id="EXREQ-PA-TRACE",
            idempotency_key="IDEM-PA-TRACE",
            risk_decision_id="RD-PA-TRACE",
            signal_id="SIG-PA-TRACE",
            symbol="TCS",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=10,
            approved_quantity=10,
            execution_quantity=10,
            limit_price=3500.0,
            timestamp=self.now
        )
        res = self.adapter.execute_order(req)
        self.assertEqual(res.execution_request_id, "EXREQ-PA-TRACE")
        self.assertEqual(res.risk_decision_id, "RD-PA-TRACE")
        self.assertIsNotNone(res.broker_order_id)


if __name__ == "__main__":
    unittest.main()
