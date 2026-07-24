# tests/test_execution_contracts.py
"""
Unit Test Suite for NexTrade Execution Domain Contracts (Sub-Phase 3A).
Verifies contract invariants, quantity constraints, fill math validation, immutability,
and Invariant E9 (status UNKNOWN requires mandatory reconciliation).
"""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import unittest

from contracts.order import OrderSide
from contracts.execution import ExecutionStatus, ExecutionRequest, ExecutionResult


class TestExecutionContracts(unittest.TestCase):

    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_valid_execution_request(self):
        req = ExecutionRequest(
            execution_request_id="EXREQ-01",
            idempotency_key="IDEM-01",
            risk_decision_id="RD-01",
            signal_id="SIG-01",
            strategy_id="STRAT-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            order_type="LIMIT",
            limit_price=2500.0,
            timestamp=self.now
        )
        self.assertEqual(req.execution_request_id, "EXREQ-01")
        self.assertEqual(req.execution_quantity, 50)
        self.assertEqual(req.to_dict()["idempotency_key"], "IDEM-01")

    def test_zero_or_negative_execution_quantity_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionRequest(
                execution_request_id="EXREQ-01",
                idempotency_key="IDEM-01",
                risk_decision_id="RD-01",
                symbol="RELIANCE",
                exchange="NSE",
                order_side=OrderSide.BUY,
                requested_quantity=100,
                approved_quantity=50,
                execution_quantity=0
            )

    def test_execution_quantity_exceeding_approved_quantity_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionRequest(
                execution_request_id="EXREQ-01",
                idempotency_key="IDEM-01",
                risk_decision_id="RD-01",
                symbol="RELIANCE",
                exchange="NSE",
                order_side=OrderSide.BUY,
                requested_quantity=100,
                approved_quantity=50,
                execution_quantity=60  # > 50 -> Violation
            )

    def test_approved_quantity_exceeding_requested_quantity_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionRequest(
                execution_request_id="EXREQ-01",
                idempotency_key="IDEM-01",
                risk_decision_id="RD-01",
                symbol="RELIANCE",
                exchange="NSE",
                order_side=OrderSide.BUY,
                requested_quantity=100,
                approved_quantity=120,  # > 100 -> Violation
                execution_quantity=100
            )

    def test_missing_mandatory_ids_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionRequest(
                execution_request_id="",  # Empty
                idempotency_key="IDEM-01",
                risk_decision_id="RD-01",
                symbol="RELIANCE",
                exchange="NSE",
                order_side=OrderSide.BUY,
                requested_quantity=100,
                approved_quantity=50,
                execution_quantity=50
            )

    def test_invalid_limit_price_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionRequest(
                execution_request_id="EXREQ-01",
                idempotency_key="IDEM-01",
                risk_decision_id="RD-01",
                symbol="RELIANCE",
                exchange="NSE",
                order_side=OrderSide.BUY,
                requested_quantity=100,
                approved_quantity=50,
                execution_quantity=50,
                limit_price=-2500.0  # Negative -> Invalid
            )

    def test_execution_request_immutability(self):
        req = ExecutionRequest(
            execution_request_id="EXREQ-01",
            idempotency_key="IDEM-01",
            risk_decision_id="RD-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50
        )
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            req.execution_quantity = 500

    def test_valid_execution_result_filled(self):
        res = ExecutionResult(
            execution_id="EXEC-01",
            execution_request_id="EXREQ-01",
            risk_decision_id="RD-01",
            status=ExecutionStatus.FILLED,
            requested_quantity=100,
            execution_quantity=50,
            filled_quantity=50,
            remaining_quantity=0,
            average_fill_price=2505.50,
            broker_order_id="BRK-999"
        )
        self.assertEqual(res.status, ExecutionStatus.FILLED)
        self.assertFalse(res.requires_reconciliation)
        self.assertEqual(res.to_dict()["broker_order_id"], "BRK-999")

    def test_filled_quantity_exceeding_execution_quantity_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionResult(
                execution_id="EXEC-01",
                execution_request_id="EXREQ-01",
                risk_decision_id="RD-01",
                status=ExecutionStatus.FILLED,
                requested_quantity=100,
                execution_quantity=50,
                filled_quantity=60,  # > 50 -> Violation
                remaining_quantity=0,
                average_fill_price=2500.0
            )

    def test_remaining_quantity_mismatch_raises_error(self):
        with self.assertRaises(ValueError):
            ExecutionResult(
                execution_id="EXEC-01",
                execution_request_id="EXREQ-01",
                risk_decision_id="RD-01",
                status=ExecutionStatus.PARTIALLY_FILLED,
                requested_quantity=100,
                execution_quantity=50,
                filled_quantity=30,
                remaining_quantity=10,  # Expected 20 -> Violation
                average_fill_price=2500.0
            )

    def test_status_unknown_requires_mandatory_reconciliation(self):
        """Invariant E9: Status UNKNOWN sets requires_reconciliation == True."""
        res_unknown = ExecutionResult(
            execution_id="EXEC-01",
            execution_request_id="EXREQ-01",
            risk_decision_id="RD-01",
            status=ExecutionStatus.UNKNOWN,
            requested_quantity=100,
            execution_quantity=50,
            filled_quantity=0,
            remaining_quantity=50,
            average_fill_price=0.0,
            rejection_reason="Network timeout on broker submission"
        )
        self.assertTrue(res_unknown.requires_reconciliation)
        self.assertEqual(res_unknown.status, ExecutionStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
