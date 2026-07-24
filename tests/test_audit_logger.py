# tests/test_audit_logger.py
"""
Unit Test Suite for NexTrade Phase 2F Risk Audit Trail Engine.
Tests append-only durability, SHA-256 hash chain continuity, cryptographic tamper detection,
sequence monotonicity, CSV projection isolation, and thread-safety concurrency.
"""
import csv
from dataclasses import FrozenInstanceError
import json
import os
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent
from risk.audit_logger import (
    RiskAuditLogger,
    AuditEvent,
    AuditIntegrityResult,
    AuditHealthStatus,
    GENESIS_HASH,
)


class TestRiskAuditLogger(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.jsonl_path = os.path.join(self.temp_dir, "risk_decisions.jsonl")
        self.csv_path = os.path.join(self.temp_dir, "risk_decisions.csv")
        self.logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)

        self.now = datetime.now(timezone.utc)
        self.decision_approved = RiskDecision(
            decision_id="RD-TEST01",
            signal_id="SIG-01",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=100,
            modification_reason="Order fully approved",
            timestamp=self.now
        )
        self.decision_modified = RiskDecision(
            decision_id="RD-TEST02",
            signal_id="SIG-02",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.MODIFIED,
            requested_quantity=100,
            approved_quantity=50,
            modification_reason="Quantity modified from 100 to 50 by PHASE_2C",
            timestamp=self.now
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_jsonl_output_format_and_genesis(self):
        event = self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")

        self.assertTrue(os.path.exists(self.jsonl_path))
        self.assertEqual(event.sequence_number, 1)
        self.assertEqual(event.previous_hash, GENESIS_HASH)
        self.assertTrue(event.audit_event_id.startswith("AE-"))
        self.assertTrue(len(event.event_hash) == 64)

        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1)
            data = json.loads(lines[0])
            self.assertEqual(data["sequence_number"], 1)
            self.assertEqual(data["decision_status"], "APPROVED")

    def test_csv_reporting_projection_format(self):
        self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")

        self.assertTrue(os.path.exists(self.csv_path))
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0]["symbol"], "RELIANCE")
            self.assertEqual(reader[0]["approved_quantity"], "100")
            self.assertEqual(reader[0]["decision_status"], "APPROVED")

    def test_sequence_monotonicity_and_hash_chaining(self):
        e1 = self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")
        e2 = self.logger.log_decision(self.decision_modified, symbol="TCS", strategy_id="STRAT_01")

        self.assertEqual(e1.sequence_number, 1)
        self.assertEqual(e2.sequence_number, 2)

        self.assertEqual(e1.previous_hash, GENESIS_HASH)
        self.assertEqual(e2.previous_hash, e1.event_hash)

        res = self.logger.verify_integrity()
        self.assertTrue(res.is_valid)
        self.assertEqual(res.total_records_checked, 2)

    def test_tamper_detection_in_hash_chain(self):
        self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")
        self.logger.log_decision(self.decision_modified, symbol="TCS", strategy_id="STRAT_01")

        # Tamper with Event 1 in JSONL file
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        d1 = json.loads(lines[0])
        d1["approved_quantity"] = 9999  # Tamper quantity
        lines[0] = json.dumps(d1) + "\n"

        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        res = self.logger.verify_integrity()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.first_invalid_sequence, 1)
        self.assertIn("tampering detected", res.error_reason.lower())

    def test_restart_durability(self):
        e1 = self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")

        # Instantiate a new logger reading the existing log files
        new_logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)
        self.assertEqual(new_logger._sequence_number, 1)
        self.assertEqual(new_logger._previous_hash, e1.event_hash)

        e2 = new_logger.log_decision(self.decision_modified, symbol="TCS", strategy_id="STRAT_01")
        self.assertEqual(e2.sequence_number, 2)
        self.assertEqual(e2.previous_hash, e1.event_hash)

        res = new_logger.verify_integrity()
        self.assertTrue(res.is_valid)
        self.assertEqual(res.total_records_checked, 2)

    def test_csv_failure_isolation_degraded_health(self):
        with patch.object(self.logger, "_append_csv", side_effect=OSError("Disk full on CSV volume")):
            event = self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")
            self.assertIsNotNone(event.event_hash)

            # JSONL integrity remains valid
            res = self.logger.verify_integrity()
            self.assertTrue(res.is_valid)

            # Logger health moves to DEGRADED
            health = self.logger.health()
            self.assertEqual(health.status, "DEGRADED")
            self.assertEqual(health.write_failures, 1)

    def test_thread_safety_concurrency(self):
        def worker(logger, i):
            dec = RiskDecision(
                decision_id=f"RD-CONC-{i}",
                signal_id=f"SIG-{i}",
                order_intent=OrderIntent.ENTRY,
                decision=RiskDecisionStatus.APPROVED,
                requested_quantity=10,
                approved_quantity=10,
                timestamp=self.now
            )
            logger.log_decision(dec, symbol=f"SYM_{i}", strategy_id="CONC")

        threads = [threading.Thread(target=worker, args=(self.logger, i)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        res = self.logger.verify_integrity()
        self.assertTrue(res.is_valid)
        self.assertEqual(res.total_records_checked, 20)

    def test_audit_event_immutability(self):
        event = self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            event.approved_quantity = 999

    def test_health_status(self):
        self.logger.log_decision(self.decision_approved, symbol="RELIANCE", strategy_id="STRAT_01")
        health = self.logger.health()
        self.assertEqual(health.status, "HEALTHY")
        self.assertEqual(health.total_records, 1)
        self.assertEqual(health.write_failures, 0)


if __name__ == "__main__":
    unittest.main()
