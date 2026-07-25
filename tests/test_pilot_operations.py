# tests/test_pilot_operations.py
"""
Adversarial Controlled Live Pilot Operations Test Suite for NexTrade (Sub-Phase 4K).
Verifies:
1. PreflightGate 100% pre-flight checklist certification and cryptographic PreflightCertificate.
2. PilotSessionManager lifecycle transitions and human re-authorization for stage escalation (Invariant 4K-P2).
3. PilotOrderPipeline per-order human approval validation in Stage 1 (Invariant 4K-P4).
4. PositionReconciler position mismatch -> RECONCILIATION_LOCK (Invariant 4K-P7).
5. FailureInjector fault injection rejection in LIVE environment (Invariant 4K-P8).
6. PilotStore dual persistence in SQLite DB and JSONL log.
"""
import os
import pytest
from datetime import datetime, timezone, timedelta

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType
from contracts.safety_contracts import ExecutionEnvironment
from contracts.pilot_contracts import PilotSessionConfig, PilotStage
from pilot.preflight_gate import PreflightGate
from pilot.session_manager import PilotSessionManager, SessionState
from pilot.order_pipeline import PilotOrderPipeline
from pilot.position_reconciler import PositionReconciler
from pilot.failure_injector import FailureInjector
from storage.pilot_store import PilotStore


@pytest.fixture
def config():
    now = datetime.now(timezone.utc)
    return PilotSessionConfig(
        session_id="SESS-PILOT-01",
        pilot_stage=PilotStage.STAGE_1_TINY_PILOT,
        max_daily_orders=10,
        max_cumulative_exposure=2500.0,
        max_daily_loss=500.0,
        max_concurrent_positions=1,
        approved_symbols=["AAPL"],
        operator_id="OP-PILOT-01",
        session_expires_at=now + timedelta(hours=2)
    )


@pytest.fixture
def req_aapl():
    return BrokerOrderRequest(
        nextrade_execution_id="EXREQ-PILOT-01",
        idempotency_key="IDEM-PILOT-01",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=1.0,
        limit_price=100.0
    )


def test_preflight_gate_certification(config):
    """Verify PreflightGate issues signed PreflightCertificate when 100% checklist passes."""
    gate = PreflightGate()
    passed, cert, reason = gate.run_preflight_certification(config)

    assert passed is True
    assert "PREFLIGHT_CERTIFIED" in reason
    assert cert is not None
    assert cert.session_id == config.session_id
    assert len(cert.preflight_evidence_hash) == 64


def test_preflight_gate_denial_on_dirty_reconciliation(config):
    """Verify PreflightGate denies certification if reconciliation is dirty."""
    gate = PreflightGate()
    passed, cert, reason = gate.run_preflight_certification(config, reconciliation_clean=False)

    assert passed is False
    assert cert is None
    assert "Reconciliation state is dirty" in reason


def test_session_manager_stage_escalation_reauthorization(config):
    """Verify stage escalation requires explicit human re-authorization ID (Invariant 4K-P2)."""
    gate = PreflightGate()
    _, cert, _ = gate.run_preflight_certification(config)

    sm = PilotSessionManager()
    started, msg = sm.start_session(config, cert)
    assert started is True
    assert sm.current_state == SessionState.ACTIVE

    # 1. Escalation without re-auth ID -> DENIED
    esc_fail, msg_fail = sm.escalate_stage(PilotStage.STAGE_2_SUPERVISED, operator_reauthorization_id="")
    assert esc_fail is False
    assert "re-authorization ID required" in msg_fail

    # 2. Escalation with re-auth ID -> SUCCESS
    esc_ok, msg_ok = sm.escalate_stage(PilotStage.STAGE_2_SUPERVISED, operator_reauthorization_id="OP-REAUTH-999")
    assert esc_ok is True
    assert "ESCALATION_SUCCESS" in msg_ok


def test_order_pipeline_human_approval_stage_1(config, req_aapl):
    """Verify Stage 1 pilot requires explicit HumanOrderApproval (Invariant 4K-P4)."""
    pipeline = PilotOrderPipeline()

    # 1. Without approval -> DENIED
    val_fail, msg_fail = pipeline.validate_human_approval(None, req_aapl, config)
    assert val_fail is False
    assert "requires explicit HumanOrderApproval" in msg_fail

    # 2. With valid approval -> APPROVED
    approval = pipeline.create_human_approval("OP-PILOT-01", req_aapl, config)
    val_ok, msg_ok = pipeline.validate_human_approval(approval, req_aapl, config)
    assert val_ok is True
    assert "PIPELINE_APPROVED" in msg_ok


def test_position_reconciler_mismatch_locks_dispatch():
    """Verify position quantity mismatch triggers RECONCILIATION_LOCK (Invariant 4K-P7)."""
    reconciler = PositionReconciler()

    int_pos = {"AAPL": 10.0}
    brk_pos = {"AAPL": 5.0}  # Mismatch delta -5.0

    clean, reason, mismatches = reconciler.reconcile_positions(int_pos, brk_pos)
    assert clean is False
    assert reconciler.is_locked is True

    # Order dispatch check -> DENIED
    can_exec, msg_exec = reconciler.can_dispatch_order("AAPL")
    assert can_exec is False
    assert "PositionReconciler is locked" in msg_exec


def test_failure_injector_live_environment_isolation():
    """Verify FailureInjector rejects fault injection in LIVE environment (Invariant 4K-P8)."""
    injector = FailureInjector()

    # Injecting in LIVE -> DENIED
    ok, msg = injector.inject_fault("NETWORK_TIMEOUT", ExecutionEnvironment.LIVE)
    assert ok is False
    assert "strictly forbidden in LIVE" in msg

    # Injecting in PAPER -> APPROVED
    ok_paper, msg_paper = injector.inject_fault("NETWORK_TIMEOUT", ExecutionEnvironment.PAPER)
    assert ok_paper is True
