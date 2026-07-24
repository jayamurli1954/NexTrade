# tests/test_execution_gate.py
"""
Unit Test Suite for NexTrade ExecutionAuthorizationGate (Sub-Phase 2H-6).
Verifies strict Default-Deny execution firewall semantics and Authoritative Audit Persistence checks.
"""
import unittest
from datetime import datetime, timezone

from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent
from risk.audit_logger import AuditHealthStatus
from risk.execution_gate import ExecutionAuthorizationGate


class TestExecutionAuthorizationGate(unittest.TestCase):

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.decision_approved = RiskDecision(
            decision_id="RD-GATE-01",
            signal_id="SIG-01",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=100,
            timestamp=self.now
        )
        self.decision_modified = RiskDecision(
            decision_id="RD-GATE-02",
            signal_id="SIG-02",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.MODIFIED,
            requested_quantity=100,
            approved_quantity=50,
            timestamp=self.now
        )

    def test_default_deny_on_none_or_invalid_type(self):
        self.assertFalse(ExecutionAuthorizationGate.can_execute(None))
        self.assertFalse(ExecutionAuthorizationGate.can_execute("INVALID_TYPE"))

    def test_approved_and_modified_positive_quantity_permitted(self):
        self.assertTrue(ExecutionAuthorizationGate.can_execute(self.decision_approved))
        self.assertTrue(ExecutionAuthorizationGate.can_execute(self.decision_modified))

    def test_rejected_and_blocked_status_prohibited(self):
        dec_rejected = RiskDecision(
            decision_id="RD-GATE-03",
            signal_id="SIG-03",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.REJECTED,
            requested_quantity=100,
            approved_quantity=0,
            timestamp=self.now
        )
        dec_blocked = RiskDecision(
            decision_id="RD-GATE-04",
            signal_id="SIG-04",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH,
            requested_quantity=100,
            approved_quantity=0,
            timestamp=self.now
        )

        self.assertFalse(ExecutionAuthorizationGate.can_execute(dec_rejected))
        self.assertFalse(ExecutionAuthorizationGate.can_execute(dec_blocked))

    def test_authoritative_jsonl_persistence_failure_denies_execution(self):
        """Authoritative JSONL persistence failure (status=FAILED) MUST prohibit execution authorization."""
        failed_jsonl_health = AuditHealthStatus(
            status="FAILED",
            total_records=10,
            last_sequence_number=10,
            current_hash="abc",
            write_failures=1,
            last_error="JSONL write failure"
        )
        self.assertFalse(ExecutionAuthorizationGate.can_execute(self.decision_approved, audit_health=failed_jsonl_health))

    def test_degraded_csv_projection_failure_permits_execution_when_jsonl_valid(self):
        """CSV reporting projection failure (status=DEGRADED) permits execution when authoritative JSONL is valid."""
        degraded_csv_health = AuditHealthStatus(
            status="DEGRADED",
            total_records=10,
            last_sequence_number=10,
            current_hash="abc",
            write_failures=1,
            last_error="CSV write failure"
        )
        self.assertTrue(ExecutionAuthorizationGate.can_execute(self.decision_approved, audit_health=degraded_csv_health))


if __name__ == "__main__":
    unittest.main()
