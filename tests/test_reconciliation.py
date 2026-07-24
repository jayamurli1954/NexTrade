# tests/test_reconciliation.py
"""
Sub-Phase 3E Reconciliation Engine Tests.
Verifies all 12 mandatory reconciliation requirements and Invariants E29 - E33:
- Invariant E29: Reconciliation Authority Boundary
- Invariant E30: Position Quantity Conservation
- Invariant E31: Cumulative Fill Monotonicity
- Invariant E32: Authoritative Broker State & Discrepancy Escalation
- Invariant E33: Deterministic Reconciliation Idempotency Identity
"""
import pytest
from datetime import datetime, timezone
import uuid

from contracts.order import OrderSide
from contracts.position import Position, PositionSide
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from contracts.protection import ProtectionPlan, TrailingDistanceType
from contracts.reconciliation import (
    ReconciliationStatus,
    DiscrepancySeverity,
    DiscrepancyType,
    ReconciliationDiscrepancy,
    ReconciliationRequest,
    ReconciliationResult,
)
from execution.state_machine import ExecutionStateMachine, RECONCILIATION_AUTHORITY_KEY
from protection.lifecycle import ProtectionLifecycleManager, ProtectionLifecycleState
from execution.reconciler import ReconciliationEngine
from brokers.paper_adapter import PaperBrokerAdapter


def create_sample_execution_request(
    request_id: str = "EXREQ-100",
    symbol: str = "RELIANCE",
    side: OrderSide = OrderSide.BUY,
    qty: int = 100
) -> ExecutionRequest:
    return ExecutionRequest(
        execution_request_id=request_id,
        idempotency_key=f"IDEM-{request_id}",
        risk_decision_id="RISK-DEC-100",
        symbol=symbol,
        exchange="NSE",
        order_side=side,
        requested_quantity=qty,
        approved_quantity=qty,
        execution_quantity=qty,
        limit_price=2500.0
    )


def create_sample_protection_manager(
    open_qty: int = 100,
    side: PositionSide = PositionSide.LONG,
    entry_price: float = 2500.0
) -> ProtectionLifecycleManager:
    plan = ProtectionPlan(
        position_side=side,
        entry_price=entry_price,
        initial_stop_loss=2400.0,
        initial_take_profit=2700.0
    )
    return ProtectionLifecycleManager(
        position_id="POS-100",
        symbol="RELIANCE",
        exchange="NSE",
        position_side=side,
        entry_price=entry_price,
        protection_plan=plan,
        risk_decision_id="RISK-DEC-100",
        initial_open_quantity=open_qty
    )


# ----------------------------------------------------------------------
# 1. Invariant E29: Reconciliation Authority Boundary
# ----------------------------------------------------------------------

def test_invariant_e29_authority_boundary():
    """Verify only ReconciliationEngine (with valid authority key) can call reconcile_to()."""
    sm = ExecutionStateMachine(execution_request_id="EXREQ-E29", initial_status=ExecutionStatus.SUBMITTED)
    sm.transition_to(ExecutionStatus.UNKNOWN, reason="Network timeout")

    # Direct transition_to from UNKNOWN must raise ValueError
    with pytest.raises(ValueError, match="Illegal state transition"):
        sm.transition_to(ExecutionStatus.FILLED)

    # Calling reconcile_to without valid authority key must raise PermissionError
    with pytest.raises(PermissionError, match="Invariant E29 Violation"):
        sm.reconcile_to(ExecutionStatus.FILLED, authority_key="INVALID_KEY", reason="Bypass test")

    # Calling reconcile_to with valid authority key must succeed
    sm.reconcile_to(ExecutionStatus.FILLED, authority_key=RECONCILIATION_AUTHORITY_KEY, reason="Authorized")
    assert sm.current_status == ExecutionStatus.FILLED


def test_invariant_e29_reconciler_integration():
    """Verify ReconciliationEngine uses reconcile_to with authority key."""
    engine = ReconciliationEngine()
    req = create_sample_execution_request("EXREQ-E29-INT")
    sm = ExecutionStateMachine(execution_request_id=req.execution_request_id, initial_status=ExecutionStatus.SUBMITTED)
    sm.transition_to(ExecutionStatus.UNKNOWN)

    broker_override = {
        "broker_order_id": "BRK-E29",
        "status": ExecutionStatus.FILLED,
        "cumulative_filled_quantity": 100,
        "average_fill_price": 2500.0
    }

    res = engine.reconcile_request(request=req, broker_state_override=broker_override, state_machine=sm)
    assert res.status == ReconciliationStatus.RESOLVED_FILLED
    assert sm.current_status == ExecutionStatus.FILLED


# ----------------------------------------------------------------------
# 2. Invariant E30: Position Quantity Conservation
# ----------------------------------------------------------------------

def test_invariant_e30_position_quantity_conservation_entry():
    """Verify Entry position quantity conservation: Q_open_new = Q_open_old + Q_entry_filled."""
    engine = ReconciliationEngine()
    pm = create_sample_protection_manager(open_qty=0)
    req = create_sample_execution_request("EXREQ-ENTRY", side=OrderSide.BUY, qty=100)

    broker_override = {
        "broker_order_id": "BRK-ENTRY",
        "status": ExecutionStatus.FILLED,
        "cumulative_filled_quantity": 100,
        "average_fill_price": 2500.0
    }

    res = engine.reconcile_request(request=req, broker_state_override=broker_override, position_manager=pm)
    assert res.fill_delta == 100
    assert pm.open_quantity == 100
    assert pm.state == ProtectionLifecycleState.ACTIVE


def test_invariant_e30_position_quantity_conservation_exit():
    """Verify Exit position quantity conservation: Q_open_new = Q_open_old - Q_exit_filled."""
    engine = ReconciliationEngine()
    pm = create_sample_protection_manager(open_qty=100)
    req = create_sample_execution_request("EXREQ-EXIT", side=OrderSide.SELL, qty=100)

    broker_override = {
        "broker_order_id": "BRK-EXIT",
        "status": ExecutionStatus.FILLED,
        "cumulative_filled_quantity": 100,
        "average_fill_price": 2500.0
    }

    res = engine.reconcile_request(request=req, broker_state_override=broker_override, position_manager=pm, is_exit_order=True)
    assert res.fill_delta == 100
    assert pm.open_quantity == 0
    assert pm.state == ProtectionLifecycleState.CLOSED


# ----------------------------------------------------------------------
# 3. Invariant E31: Cumulative Fill Monotonicity
# ----------------------------------------------------------------------

def test_invariant_e31_cumulative_fill_monotonicity():
    """Verify cumulative fill delta calculation prevents double-counting fills."""
    engine = ReconciliationEngine()
    pm = create_sample_protection_manager(open_qty=100)
    req = create_sample_execution_request("EXREQ-E31", side=OrderSide.SELL, qty=100)

    # First broker event: Partial fill 40
    event1 = {
        "broker_order_id": "BRK-E31",
        "status": ExecutionStatus.PARTIALLY_FILLED,
        "cumulative_filled_quantity": 40,
        "average_fill_price": 2500.0,
        "broker_event_id": "EVT-1"
    }

    res1 = engine.process_broker_event(broker_event=event1, request=req, position_manager=pm, is_exit_order=True)
    assert res1.fill_delta == 40
    assert pm.open_quantity == 60

    # Second broker event: Complete fill 100
    event2 = {
        "broker_order_id": "BRK-E31",
        "status": ExecutionStatus.FILLED,
        "cumulative_filled_quantity": 100,
        "average_fill_price": 2500.0,
        "broker_event_id": "EVT-2"
    }

    res2 = engine.process_broker_event(broker_event=event2, request=req, position_manager=pm, is_exit_order=True)
    assert res2.fill_delta == 60  # 100 - 40
    assert pm.open_quantity == 0
    assert pm.state == ProtectionLifecycleState.CLOSED


# ----------------------------------------------------------------------
# 4. Invariant E32: Authoritative Broker State & Discrepancy Escalation
# ----------------------------------------------------------------------

def test_invariant_e32_discrepancy_detection():
    """Verify position discrepancies are audited and escalated without silent overwrites."""
    engine = ReconciliationEngine()

    internal_positions = [
        Position(position_id="POS-1", strategy_id="STRAT-1", symbol="RELIANCE", exchange="NSE", quantity=100, side=PositionSide.LONG, average_entry_price=2500.0, current_price=2550.0),
        Position(position_id="POS-2", strategy_id="STRAT-1", symbol="TCS", exchange="NSE", quantity=50, side=PositionSide.LONG, average_entry_price=3500.0, current_price=3600.0),
    ]

    broker_positions = [
        Position(position_id="POS-1", strategy_id="STRAT-1", symbol="RELIANCE", exchange="NSE", quantity=60, side=PositionSide.LONG, average_entry_price=2500.0, current_price=2550.0),
    ]

    discrepancies = engine.detect_discrepancies(internal_positions=internal_positions, broker_positions=broker_positions)
    assert len(discrepancies) == 2


    qty_disc = next(d for d in discrepancies if d.discrepancy_type == DiscrepancyType.QUANTITY_MISMATCH)
    assert qty_disc.severity == DiscrepancySeverity.CRITICAL
    assert qty_disc.expected_value == 100
    assert qty_disc.actual_value == 60

    unmatched_disc = next(d for d in discrepancies if d.discrepancy_type == DiscrepancyType.UNMATCHED_ORDER)
    assert unmatched_disc.severity == DiscrepancySeverity.CRITICAL
    assert unmatched_disc.expected_value == 50
    assert unmatched_disc.actual_value == 0


# ----------------------------------------------------------------------
# 5. Invariant E33: Deterministic Reconciliation Idempotency Identity
# ----------------------------------------------------------------------

def test_invariant_e33_idempotency_identity():
    """Verify processing identical broker state produces identical key and cached result without side effects."""
    engine = ReconciliationEngine()
    pm = create_sample_protection_manager(open_qty=100)
    req = create_sample_execution_request("EXREQ-E33", side=OrderSide.SELL, qty=100)

    broker_state = {
        "broker_order_id": "BRK-E33",
        "status": ExecutionStatus.FILLED,
        "cumulative_filled_quantity": 100,
        "average_fill_price": 2500.0,
        "broker_event_id": "EVT-STABLE"
    }

    res1 = engine.reconcile_request(request=req, broker_state_override=broker_state, position_manager=pm, is_exit_order=True)
    assert res1.fill_delta == 100
    assert pm.open_quantity == 0

    # Execute second time with identical broker state
    res2 = engine.reconcile_request(request=req, broker_state_override=broker_state, position_manager=pm, is_exit_order=True)
    assert res2.reconciliation_key == res1.reconciliation_key
    assert res2.reconciliation_id == res1.reconciliation_id
    assert pm.open_quantity == 0  # Position remains 0, not negative


# ----------------------------------------------------------------------
# 6. UNKNOWN Exit Resolution & Protection Restoration
# ----------------------------------------------------------------------

def test_unknown_exit_rejection_restores_active_protection():
    """Verify exit rejection restores ProtectionLifecycleManager state from RECONCILIATION_REQUIRED to ACTIVE."""
    engine = ReconciliationEngine()
    pm = create_sample_protection_manager(open_qty=100)
    pm.state = ProtectionLifecycleState.RECONCILIATION_REQUIRED

    req = create_sample_execution_request("EXREQ-REJ-EXIT", side=OrderSide.SELL, qty=100)

    broker_override = {
        "broker_order_id": "BRK-REJ",
        "status": ExecutionStatus.REJECTED,
        "cumulative_filled_quantity": 0,
        "average_fill_price": 0.0,
        "details": "Broker margin error"
    }

    res = engine.reconcile_request(request=req, broker_state_override=broker_override, position_manager=pm, is_exit_order=True)
    assert res.status == ReconciliationStatus.RESOLVED_REJECTED
    assert pm.open_quantity == 100
    assert pm.state == ProtectionLifecycleState.ACTIVE  # Restored to ACTIVE for future protection evaluation


# ----------------------------------------------------------------------
# 7. Restart Recovery Serialization
# ----------------------------------------------------------------------

def test_reconciler_restart_recovery():
    """Verify to_dict and from_dict restore cumulative fills and state."""
    engine = ReconciliationEngine()
    req = create_sample_execution_request("EXREQ-RESTART")

    broker_override = {
        "broker_order_id": "BRK-RESTART",
        "status": ExecutionStatus.PARTIALLY_FILLED,
        "cumulative_filled_quantity": 50,
        "average_fill_price": 2500.0
    }

    engine.reconcile_request(request=req, broker_state_override=broker_override)

    serialized = engine.to_dict()
    recovered = ReconciliationEngine.from_dict(serialized)

    assert recovered._cumulative_fills[req.execution_request_id] == 50
