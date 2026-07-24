# tests/test_execution_gateway.py
"""
Unit Test Suite for NexTrade ExecutionGateway (Sub-Phase 3B).
Verifies authoritative decision binding, quantity integrity checks, delegation to ExecutionAuthorizationGate,
and Invariant E10 (Idempotency Intent Binding).
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from contracts.order import OrderSide
from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from risk.audit_logger import RiskAuditLogger, AuditHealthStatus
from execution.gateway import ExecutionGateway


class TestExecutionGateway(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.jsonl_path = os.path.join(self.temp_dir, "risk_decisions.jsonl")
        self.csv_path = os.path.join(self.temp_dir, "risk_decisions.csv")
        self.audit_logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)

        self.gateway = ExecutionGateway(audit_logger=self.audit_logger)
        self.now = datetime.now(timezone.utc)

        # Approved RiskDecision
        self.decision_approved = RiskDecision(
            decision_id="RD-GW-01",
            signal_id="SIG-01",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=50,
            timestamp=self.now
        )
        self.gateway.register_risk_decision(self.decision_approved)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_valid_execution_request_authorized(self):
        req = ExecutionRequest(
            execution_request_id="EXREQ-GW-01",
            idempotency_key="IDEM-GW-01",
            risk_decision_id="RD-GW-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            timestamp=self.now
        )
        res = self.gateway.execute(req)
        self.assertEqual(res.status, ExecutionStatus.SUBMITTED)
        self.assertEqual(res.execution_request_id, "EXREQ-GW-01")

    def test_rejected_decision_denies_execution(self):
        dec_rejected = RiskDecision(
            decision_id="RD-GW-REJ",
            signal_id="SIG-02",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.REJECTED,
            requested_quantity=100,
            approved_quantity=0,
            timestamp=self.now
        )
        self.gateway.register_risk_decision(dec_rejected)

        req = ExecutionRequest(
            execution_request_id="EXREQ-GW-02",
            idempotency_key="IDEM-GW-02",
            risk_decision_id="RD-GW-REJ",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            timestamp=self.now
        )
        res = self.gateway.execute(req)
        self.assertEqual(res.status, ExecutionStatus.REJECTED)
        self.assertTrue(any(k in res.rejection_reason for k in ("QUANTITY_EXCEEDED", "EXECUTION_GATE_DENIED")))



    def test_execution_quantity_exceeding_authoritative_approved_quantity_denies_execution(self):
        """Caller setting execution_quantity = 50 when authoritative RiskDecision.approved_quantity = 20 MUST be rejected."""
        dec_small = RiskDecision(
            decision_id="RD-GW-SMALL",
            signal_id="SIG-03",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=20,  # Authoritative cap = 20
            timestamp=self.now
        )
        self.gateway.register_risk_decision(dec_small)

        # Forged caller request attempting execution_quantity = 50
        req = ExecutionRequest(
            execution_request_id="EXREQ-GW-03",
            idempotency_key="IDEM-GW-03",
            risk_decision_id="RD-GW-SMALL",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            timestamp=self.now
        )
        res = self.gateway.execute(req)
        self.assertEqual(res.status, ExecutionStatus.REJECTED)
        self.assertIn("QUANTITY_EXCEEDED", res.rejection_reason)

    def test_unknown_risk_decision_id_denies_execution(self):
        req = ExecutionRequest(
            execution_request_id="EXREQ-GW-04",
            idempotency_key="IDEM-GW-04",
            risk_decision_id="RD-UNKNOWN-ID",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            timestamp=self.now
        )
        res = self.gateway.execute(req)
        self.assertEqual(res.status, ExecutionStatus.REJECTED)
        self.assertIn("UNKNOWN_RISK_DECISION", res.rejection_reason)

    def test_idempotency_identical_resubmission_returns_cached_result(self):
        req = ExecutionRequest(
            execution_request_id="EXREQ-GW-05",
            idempotency_key="IDEM-REPEAT-01",
            risk_decision_id="RD-GW-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,
            timestamp=self.now
        )
        res1 = self.gateway.execute(req)
        res2 = self.gateway.execute(req)

        self.assertEqual(res1.execution_id, res2.execution_id)
        self.assertEqual(res1.status, res2.status)

    def test_idempotency_conflict_rejection(self):
        """Invariant E10: Reusing idempotency_key with conflicting payload MUST be rejected."""
        req1 = ExecutionRequest(
            execution_request_id="EXREQ-GW-06A",
            idempotency_key="IDEM-CONFLICT-01",
            risk_decision_id="RD-GW-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=10,  # original quantity = 10
            timestamp=self.now
        )
        res1 = self.gateway.execute(req1)
        self.assertEqual(res1.status, ExecutionStatus.SUBMITTED)

        # Conflicting request reusing same idempotency_key with execution_quantity = 50
        req2 = ExecutionRequest(
            execution_request_id="EXREQ-GW-06B",
            idempotency_key="IDEM-CONFLICT-01",
            risk_decision_id="RD-GW-01",
            symbol="RELIANCE",
            exchange="NSE",
            order_side=OrderSide.BUY,
            requested_quantity=100,
            approved_quantity=50,
            execution_quantity=50,  # conflicting quantity = 50
            timestamp=self.now
        )
        res2 = self.gateway.execute(req2)
        self.assertEqual(res2.status, ExecutionStatus.REJECTED)
        self.assertIn("IDEMPOTENCY_CONFLICT", res2.rejection_reason)


if __name__ == "__main__":
    unittest.main()
