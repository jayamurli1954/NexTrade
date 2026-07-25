# tests/test_state_machine_invariants.py
"""
Unit Test Suite for State Machine Invariants (E24 - E28).
Validates ExecutionStateMachine graph integrity, terminal state bounds,
idempotent self-transitions, lineage records, and constructor identity validation.
"""
import pytest
from contracts.execution import ExecutionStatus
from execution.state_machine import (
    ExecutionStateMachine,
    RECONCILIATION_AUTHORITY_KEY,
)


def test_e24_state_transition_graph_integrity():
    """
    E24: State Transition Graph Integrity.
    Valid transitions succeed; illegal state jumps raise ValueError.
    """
    sm = ExecutionStateMachine(execution_request_id="req_e24_001")
    assert sm.current_status == ExecutionStatus.CREATED

    # Valid: CREATED -> AUTHORIZED -> SUBMITTED -> FILLED
    sm.transition_to(ExecutionStatus.AUTHORIZED, reason="Risk approved")
    assert sm.current_status == ExecutionStatus.AUTHORIZED

    sm.transition_to(ExecutionStatus.SUBMITTED, reason="Sent to broker")
    assert sm.current_status == ExecutionStatus.SUBMITTED

    sm.transition_to(ExecutionStatus.FILLED, reason="Fill reported")
    assert sm.current_status == ExecutionStatus.FILLED

    # Illegal transition: CREATED -> FILLED directly (new SM instance)
    sm2 = ExecutionStateMachine(execution_request_id="req_e24_002")
    with pytest.raises(ValueError, match="Illegal state transition"):
        sm2.transition_to(ExecutionStatus.FILLED)

    # Illegal transition: CREATED -> SUBMITTED directly
    sm3 = ExecutionStateMachine(execution_request_id="req_e24_003")
    with pytest.raises(ValueError, match="Illegal state transition"):
        sm3.transition_to(ExecutionStatus.SUBMITTED)


def test_e25_terminal_state_immutability_and_reconciliation_boundary():
    """
    E25: Terminal State Immutability & Reconciliation Boundary.
    Terminal states permit 0 outward transitions via transition_to().
    UNKNOWN can only be resolved via reconcile_to() with valid authority key.
    """
    # 1. Test FILLED terminal state
    sm_filled = ExecutionStateMachine(execution_request_id="req_e25_filled")
    sm_filled.transition_to(ExecutionStatus.AUTHORIZED)
    sm_filled.transition_to(ExecutionStatus.SUBMITTED)
    sm_filled.transition_to(ExecutionStatus.FILLED)
    assert sm_filled.is_terminal is True

    with pytest.raises(ValueError, match="Illegal state transition"):
        sm_filled.transition_to(ExecutionStatus.SUBMITTED)

    # 2. Test UNKNOWN state
    sm_unknown = ExecutionStateMachine(execution_request_id="req_e25_unknown")
    sm_unknown.transition_to(ExecutionStatus.AUTHORIZED)
    sm_unknown.transition_to(ExecutionStatus.SUBMITTED)
    sm_unknown.transition_to(ExecutionStatus.UNKNOWN, reason="Timeout")
    assert sm_unknown.is_terminal is True

    # Direct transition_to from UNKNOWN must fail
    with pytest.raises(ValueError, match="Illegal state transition"):
        sm_unknown.transition_to(ExecutionStatus.FILLED)

    # Unauthorized reconcile_to must fail (Invariant E29)
    with pytest.raises(PermissionError, match="Invariant E29 Violation"):
        sm_unknown.reconcile_to(ExecutionStatus.FILLED, authority_key="INVALID_KEY")

    # Authorized reconcile_to succeeds
    resolved = sm_unknown.reconcile_to(
        ExecutionStatus.FILLED,
        authority_key=RECONCILIATION_AUTHORITY_KEY,
        reason="Verified via broker query"
    )
    assert resolved == ExecutionStatus.FILLED
    assert sm_unknown.current_status == ExecutionStatus.FILLED


def test_e26_idempotent_state_self_transitions():
    """
    E26: Idempotent State Self-Transitions.
    Transitioning to current state returns current state cleanly without appending duplicate history.
    """
    sm = ExecutionStateMachine(execution_request_id="req_e26_001")
    sm.transition_to(ExecutionStatus.AUTHORIZED)
    initial_history_len = len(sm.get_history())

    # Self-transition to AUTHORIZED
    res = sm.transition_to(ExecutionStatus.AUTHORIZED, reason="Duplicate trigger")
    assert res == ExecutionStatus.AUTHORIZED
    assert len(sm.get_history()) == initial_history_len


def test_e27_complete_lineage_audit_trail():
    """
    E27: Complete Lineage Audit Trail.
    Every transition records timestamped ExecutionStateRecord.
    """
    sm = ExecutionStateMachine(execution_request_id="req_e27_001")
    sm.transition_to(ExecutionStatus.AUTHORIZED, reason="Authorization gate pass")
    sm.transition_to(ExecutionStatus.SUBMITTED, reason="Broker submission")

    history = sm.get_history()
    assert len(history) == 3
    assert history[0].previous_status is None
    assert history[0].new_status == ExecutionStatus.CREATED
    assert history[0].reason == "INITIAL_STATE"

    assert history[1].previous_status == ExecutionStatus.CREATED
    assert history[1].new_status == ExecutionStatus.AUTHORIZED
    assert history[1].reason == "Authorization gate pass"

    assert history[2].previous_status == ExecutionStatus.AUTHORIZED
    assert history[2].new_status == ExecutionStatus.SUBMITTED
    assert history[2].reason == "Broker submission"

    for record in history:
        assert record.execution_request_id == "req_e27_001"
        assert record.timestamp is not None


def test_e28_non_empty_identity_enforcement():
    """
    E28: Non-Empty Identifier Enforcement.
    Initializing ExecutionStateMachine with empty or None ID raises ValueError.
    """
    with pytest.raises(ValueError, match="execution_request_id must be a non-empty string"):
        ExecutionStateMachine(execution_request_id="")

    with pytest.raises(ValueError, match="execution_request_id must be a non-empty string"):
        ExecutionStateMachine(execution_request_id=None)
