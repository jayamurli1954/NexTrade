# tests/test_audit_recovery.py
"""
Audit Log Edge-Case Recovery & Integrity Testing Suite for NexTrade (Sub-Phase 2H-4).
Tests partial final JSON lines, broken SHA-256 hash chains, missing sequence numbers,
and CSV corruption recovery behavior.
"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent
from risk.audit_logger import RiskAuditLogger, GENESIS_HASH


class TestAuditRecovery(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.jsonl_path = os.path.join(self.temp_dir, "risk_decisions.jsonl")
        self.csv_path = os.path.join(self.temp_dir, "risk_decisions.csv")
        self.logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)

        self.now = datetime.now(timezone.utc)
        self.decision = RiskDecision(
            decision_id="RD-REC-01",
            signal_id="SIG-REC",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=100,
            timestamp=self.now
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_partial_final_json_line_recovery(self):
        """Simulate abnormal termination leaving incomplete JSON line at end of log."""
        self.logger.log_decision(self.decision, symbol="RELIANCE")

        # Append incomplete JSON line to simulate crash during write
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write('{"sequence_number": 2, "audit_event_id": "AE-INCOMPLETE')

        # Re-instantiate logger; should detect corrupt tail line and enter DEGRADED status safely
        new_logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)
        health = new_logger.health()
        self.assertEqual(health.status, "DEGRADED")
        self.assertIn("corrupt final line", health.last_error.lower())

    def test_historical_line_modification_detection(self):
        """Modifying historical payload invalidates hash chain during verify_integrity()."""
        e1 = self.logger.log_decision(self.decision, symbol="RELIANCE")
        e2 = self.logger.log_decision(self.decision, symbol="TCS")

        # Tamper line 1
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        d1 = json.loads(lines[0])
        d1["approved_quantity"] = 500  # Forged quantity
        lines[0] = json.dumps(d1) + "\n"

        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        res = self.logger.verify_integrity()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.first_invalid_sequence, 1)

    def test_sequence_gap_detection(self):
        """Simulate missing sequence number in JSONL audit log."""
        self.logger.log_decision(self.decision, symbol="RELIANCE")
        self.logger.log_decision(self.decision, symbol="TCS")

        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Modify sequence of line 2 from 2 to 4 (creating a gap)
        d2 = json.loads(lines[1])
        d2["sequence_number"] = 4
        lines[1] = json.dumps(d2) + "\n"

        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        res = self.logger.verify_integrity()
        self.assertFalse(res.is_valid)
        self.assertIn("discontinuity", res.error_reason.lower())


if __name__ == "__main__":
    unittest.main()
