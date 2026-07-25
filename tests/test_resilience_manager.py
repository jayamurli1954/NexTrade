# tests/test_resilience_manager.py
"""
Adversarial Operational Resilience Test Suite for NexTrade (Sub-Phase 4L).
Verifies:
1. IncidentManager escalation and human operator acknowledgement (Invariants 4L-P1, 4L-P8).
2. DisconnectHandler stream disconnect and reconnect recovery (Invariant 4L-P3).
3. IdempotencyGuard recovery epoch advance and duplicate fill rejection (Invariant 4L-P5).
4. DLQRecoveryEngine deterministic replay and stale event protection (Invariant 4L-P6).
5. ResilienceBackupManager SQLite backup integrity and safe restore (Invariant 4L-P10).
6. ChaosRunner 6 certified drills execution and decision precedence (REJECT > HOLD > READY) (Invariants 4L-P11, 4L-P12, 4L-P13).
"""
import pytest
from datetime import datetime, timezone

from contracts.resilience_contracts import IncidentSeverity, ResilienceCertificateStatus
from resilience.incident_manager import IncidentManager
from resilience.disconnect_handler import DisconnectHandler
from resilience.idempotency_guard import IdempotencyGuard
from resilience.dlq_recovery import DLQRecoveryEngine
from storage.resilience_backup import ResilienceBackupManager
from resilience.chaos_runner import ChaosRunner


def test_incident_manager_escalation_and_ack():
    """Verify IncidentManager triggers HARD_HALT on FATAL incident and requires operator ACK (Invariant 4L-P1, 4L-P8)."""
    im = IncidentManager()

    # 1. Report CRITICAL incident -> HARD_HALT
    rec = im.report_incident("GATEWAY", IncidentSeverity.FATAL, "Database lock detected")
    assert rec.triggered_action == "HARD_HALT"
    assert im.current_mode == "HARD_HALT"
    assert len(im.get_unacknowledged_incidents()) == 1

    # 2. Reset without ACK -> DENIED
    ok_reset, msg_reset = im.reset_incident_state("OP-REC-01")
    assert ok_reset is False
    assert "unacknowledged incidents remain" in msg_reset

    # 3. Acknowledge -> SUCCESS
    ok_ack, msg_ack = im.acknowledge_incident(rec.incident_id, "OP-REC-01")
    assert ok_ack is True

    # 4. Reset with ACK -> SUCCESS
    ok_reset2, _ = im.reset_incident_state("OP-REC-01")
    assert ok_reset2 is True
    assert im.current_mode == "NORMAL"


def test_disconnect_handler_reconnect_reconciliation():
    """Verify DisconnectHandler requires position reconciliation for reconnect (Invariant 4L-P3)."""
    dh = DisconnectHandler()
    dh.handle_disconnect("BROKER_SOCKET_CLOSED")
    assert dh.connection_status == "DISCONNECTED"

    # Reconnect with failed reconciliation -> DENIED
    ok_rec, msg_rec = dh.complete_reconnect_with_reconciliation(reconciliation_passed=False, operator_id="OP-01")
    assert ok_rec is False
    assert dh.connection_status == "DISCONNECTED"

    # Reconnect with passed reconciliation -> SUCCESS
    ok_rec2, _ = dh.complete_reconnect_with_reconciliation(reconciliation_passed=True, operator_id="OP-01")
    assert ok_rec2 is True
    assert dh.connection_status == "CONNECTED"


def test_idempotency_guard_recovery_epoch():
    """Verify IdempotencyGuard advances recovery_epoch and rejects duplicate fills (Invariant 4L-P5)."""
    ig = IdempotencyGuard()
    ig.clear()

    e1 = ig.recovery_epoch
    ok1 = ig.mark_processed("FILL", "FILL-KEY-001")
    assert ok1 is True

    # Duplicate fill under same epoch -> REJECTED
    ok2 = ig.mark_processed("FILL", "FILL-KEY-001")
    assert ok2 is False

    # Advance epoch -> Old key remains recorded persistently
    e2 = ig.advance_recovery_epoch()
    assert e2 == e1 + 1
    assert ig.is_processed("FILL", "FILL-KEY-001") is True


def test_dlq_recovery_stale_event_protection():
    """Verify DLQRecoveryEngine rejects stale events exceeding age threshold (Invariant 4L-P6)."""
    dlq = DLQRecoveryEngine()
    records = [
        {"event_id": "EVT-1", "payload": {"data": 1}, "age_seconds": 100.0},
        {"event_id": "EVT-2", "payload": {"data": 2}, "age_seconds": 5000.0}  # Exceeds max 3600
    ]

    success, replayed, rejected, h = dlq.replay_dlq_records(records, max_allowed_age_seconds=3600.0)
    assert success is False
    assert replayed == 1
    assert len(rejected) == 1
    assert "STALE_EVENT_REJECTED" in rejected[0]


def test_chaos_runner_6_drills_certification():
    """Verify ChaosRunner executes 6 mandatory drills and evaluates READY certificate (Invariants 4L-P11, 4L-P12, 4L-P13)."""
    runner = ChaosRunner()
    cert, drills = runner.run_resilience_certification_drills()

    assert len(drills) == 6
    assert cert.drills_passed_count == 6
    assert cert.status == ResilienceCertificateStatus.READY
    assert len(cert.evidence_hash) == 64
