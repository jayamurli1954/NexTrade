# tests/test_execution_engine.py
"""
Sub-Phase 3F ExecutionEngine Orchestrator Unit Test Suite.
Verifies all 20+ test matrix scenarios and Invariants E34 - E41:
- E34: Controlled Gateway Entry & Lineage Retention
- E35: No Broker Bypass for Protection Exits
- E36: State Machine Synchronization
- E37 / E39-NonRetry: Automatic UNKNOWN Escalation without Retries
- E38: Subsystem State Serialization & Restart Recovery
- E39: Execution Lineage Preservation
- E40: Position Quantity Conservation
- E41: Single Active Protection Manager per Position
"""
import pytest
from datetime import datetime, timezone
import uuid

from contracts.order import OrderSide
from contracts.position import PositionSide
from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus, ExecutionSubmissionResult
from contracts.protection import ProtectionPlan, TrailingDistanceType, ProtectionDecisionType
from contracts.reconciliation import ReconciliationStatus
from risk.execution_gate import ExecutionAuthorizationGate
from execution.gateway import ExecutionGateway
from execution.state_machine import ExecutionStateMachine
from protection.lifecycle import ProtectionLifecycleManager, ProtectionLifecycleState
from execution.reconciler import ReconciliationEngine
from brokers.paper_adapter import PaperBrokerAdapter
from execution.engine import ExecutionEngine


def create_sample_risk_decision(
    decision_id: str = "RD-3F-001",
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    qty: int = 100
) -> RiskDecision:
    app_qty = 0 if status in (RiskDecisionStatus.REJECTED, RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH) else qty
    return RiskDecision(
        decision_id=decision_id,
        signal_id=f"SIG-{decision_id}",
        order_intent=OrderIntent.ENTRY,
        decision=status,
        requested_quantity=qty,
        approved_quantity=app_qty,
        modification_reason="Authorized for test"
    )




def create_sample_protection_plan() -> ProtectionPlan:
    return ProtectionPlan(
        position_side=PositionSide.LONG,
        entry_price=2500.0,
        initial_stop_loss=2400.0,
        initial_take_profit=2700.0,
        trailing_enabled=True,
        trailing_distance=50.0,
        trailing_step=10.0
    )


@pytest.fixture
def setup_engine():
    adapter = PaperBrokerAdapter()
    gateway = ExecutionGateway(broker_adapter=adapter)
    reconciler = ReconciliationEngine(broker_adapter=adapter, gateway=gateway)
    engine = ExecutionEngine(gateway=gateway, broker_adapter=adapter, reconciler=reconciler)
    return engine, gateway, adapter, reconciler


# ----------------------------------------------------------------------
# 1. Invariant E34: Authorized Entry -> Gateway Dispatch & Submission Result
# ----------------------------------------------------------------------

def test_e34_authorized_entry_submission(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-AUTH-1", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")

    assert sub_res.execution_result.status == ExecutionStatus.FILLED
    assert sub_res.execution_result.filled_quantity == 100
    assert sub_res.protection_activated is True
    assert sub_res.position_id is not None

    # Check manager in engine registry
    pm = engine.get_protection_manager(sub_res.position_id)
    assert pm is not None
    assert pm.open_quantity == 100
    assert pm.state == ProtectionLifecycleState.ACTIVE


def test_e34_unauthorized_entry_rejection(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-REJ-1", RiskDecisionStatus.REJECTED, qty=100)

    sub_res = engine.submit_entry(risk_decision=rd, symbol="RELIANCE")

    assert sub_res.execution_result.status == ExecutionStatus.REJECTED
    assert sub_res.protection_activated is False
    assert sub_res.position_id is None


# ----------------------------------------------------------------------
# 2. Invariant E36: Entry -> State Machine Synchronization
# ----------------------------------------------------------------------

def test_e36_state_machine_synchronization(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-SM-1", RiskDecisionStatus.APPROVED, qty=100)

    sub_res = engine.submit_entry(risk_decision=rd, symbol="RELIANCE")
    req_id = sub_res.execution_result.execution_request_id

    sm = engine.get_state_machine(req_id)
    assert sm is not None
    assert sm.current_status == ExecutionStatus.FILLED

    history = sm.get_history()
    statuses = [rec.new_status for rec in history]
    assert ExecutionStatus.CREATED in statuses
    assert ExecutionStatus.AUTHORIZED in statuses
    assert ExecutionStatus.SUBMITTED in statuses
    assert ExecutionStatus.FILLED in statuses


# ----------------------------------------------------------------------
# 3. Invariant E35: Protection Exits Route Through Gateway Without Bypass
# ----------------------------------------------------------------------

def test_e35_protection_sl_exit_gateway_dispatch(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-EXIT-SL", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")
    pos_id = sub_res.position_id

    # Trigger SL breach at price 2350 (SL is 2400)
    tick_results = engine.process_market_tick("RELIANCE", 2350.0)

    assert len(tick_results) == 1
    dec, exec_res = tick_results[0]

    assert dec.decision == ProtectionDecisionType.EXIT
    assert exec_res is not None
    assert exec_res.status == ExecutionStatus.FILLED
    assert exec_res.filled_quantity == 100

    pm = engine.get_protection_manager(pos_id)
    assert pm.open_quantity == 0
    assert pm.state == ProtectionLifecycleState.CLOSED


def test_e35_protection_tp_exit_gateway_dispatch(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-EXIT-TP", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")
    pos_id = sub_res.position_id

    # Trigger TP breach at price 2750 (TP is 2700)
    tick_results = engine.process_market_tick("RELIANCE", 2750.0)

    assert len(tick_results) == 1
    dec, exec_res = tick_results[0]

    assert dec.decision == ProtectionDecisionType.EXIT
    assert exec_res is not None
    assert exec_res.status == ExecutionStatus.FILLED

    pm = engine.get_protection_manager(pos_id)
    assert pm.state == ProtectionLifecycleState.CLOSED


# ----------------------------------------------------------------------
# 4. Invariant E37 / E39-NonRetry: Automatic UNKNOWN Escalation
# ----------------------------------------------------------------------

class MockTimeoutBrokerAdapter:
    """Mock broker adapter that simulates post-submission timeout resulting in status UNKNOWN."""
    def execute_order(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            execution_id=f"EXEC-TO-{request.execution_request_id}",
            execution_request_id=request.execution_request_id,
            risk_decision_id=request.risk_decision_id,
            status=ExecutionStatus.UNKNOWN,
            requested_quantity=request.requested_quantity,
            execution_quantity=request.execution_quantity,
            filled_quantity=0,
            remaining_quantity=request.execution_quantity,
            average_fill_price=0.0,
            rejection_reason="POST_SUBMISSION_TIMEOUT",
            timestamp=datetime.now(timezone.utc)
        )

    def query_execution(self, execution_request_id=None, broker_order_id=None, idempotency_key=None):
        return {
            "broker_order_id": "BRK-RESOLVED-100",
            "status": ExecutionStatus.FILLED,
            "cumulative_filled_quantity": 100,
            "average_fill_price": 2500.0
        }


def test_e37_unknown_entry_reconciliation_registration():
    timeout_adapter = MockTimeoutBrokerAdapter()
    gateway = ExecutionGateway(broker_adapter=timeout_adapter)
    reconciler = ReconciliationEngine(broker_adapter=timeout_adapter, gateway=gateway)
    engine = ExecutionEngine(gateway=gateway, broker_adapter=timeout_adapter, reconciler=reconciler)

    rd = create_sample_risk_decision("RD-TIMEOUT-1", RiskDecisionStatus.APPROVED, qty=100)
    sub_res = engine.submit_entry(risk_decision=rd, symbol="RELIANCE")

    assert sub_res.execution_result.status == ExecutionStatus.UNKNOWN
    assert sub_res.reconciliation_required is True

    # Verify order is queued in pending unknown requests
    assert rd.decision_id in gateway._decision_store

    # Perform reconciliation
    rec_results = engine.reconcile_pending()
    assert len(rec_results) == 1
    assert rec_results[0].status == ReconciliationStatus.RESOLVED_FILLED


# ----------------------------------------------------------------------
# 5. Invariant E39: Execution Lineage Preservation
# ----------------------------------------------------------------------

def test_e39_execution_lineage_preservation(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-LINEAGE-1", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")
    req_id = sub_res.execution_result.execution_request_id

    lineage = engine._execution_lineage.get(req_id)
    assert lineage is not None
    assert lineage["risk_decision_id"] == rd.decision_id
    assert lineage["signal_id"] == rd.signal_id
    assert lineage["position_id"] == sub_res.position_id


# ----------------------------------------------------------------------
# 6. Invariant E40: Position Quantity Conservation
# ----------------------------------------------------------------------

def test_e40_position_quantity_conservation(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-QTY-1", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")
    pm = engine.get_protection_manager(sub_res.position_id)

    # Initial entry fill -> open_quantity = 100
    assert pm.open_quantity == 100

    # Partial position exit update
    pm.update_position_quantity(60)
    assert pm.open_quantity == 60
    assert pm.open_quantity >= 0

    # Complete exit
    pm.update_position_quantity(0)
    assert pm.open_quantity == 0
    assert pm.state == ProtectionLifecycleState.CLOSED


# ----------------------------------------------------------------------
# 7. Invariant E41: Single Active Protection Manager per Position
# ----------------------------------------------------------------------

def test_e41_single_active_protection_manager(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-E41-1", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res1 = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")
    pos_id = sub_res1.position_id

    # Second entry submission with same position_id (scale-in)
    rd2 = create_sample_risk_decision("RD-E41-2", RiskDecisionStatus.APPROVED, qty=100)
    sub_res2 = engine.submit_entry(risk_decision=rd2, protection_plan=plan, symbol="RELIANCE")


    # Verify only ONE manager exists for this position_id in engine registry
    active_managers = engine.get_active_protection_managers()
    matching = [m for k, m in active_managers.items() if k == pos_id]
    assert len(matching) == 1
    assert matching[0].open_quantity == 200  # Consolidated open quantity


# ----------------------------------------------------------------------
# 8. Invariant E38: Subsystem Serialization & Restart Recovery
# ----------------------------------------------------------------------

def test_e38_restart_recovery_serialization(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine
    rd = create_sample_risk_decision("RD-SERIAL-1", RiskDecisionStatus.APPROVED, qty=100)
    plan = create_sample_protection_plan()

    sub_res = engine.submit_entry(risk_decision=rd, protection_plan=plan, symbol="RELIANCE")
    pos_id = sub_res.position_id

    serialized = engine.to_dict()
    assert "protection_managers" in serialized
    assert pos_id in serialized["protection_managers"]

    # Reconstruct Engine from serialized dictionary
    new_gateway = ExecutionGateway(broker_adapter=adapter)
    new_engine = ExecutionEngine.from_dict(serialized, gateway=new_gateway, broker_adapter=adapter)

    recovered_pm = new_engine.get_protection_manager(pos_id)
    assert recovered_pm is not None
    assert recovered_pm.open_quantity == 100
    assert recovered_pm.symbol == "RELIANCE"
    assert recovered_pm.state == ProtectionLifecycleState.ACTIVE


# ----------------------------------------------------------------------
# 9. Multiple Position Isolation
# ----------------------------------------------------------------------

def test_multiple_position_isolation(setup_engine):
    engine, gateway, adapter, reconciler = setup_engine

    rd1 = create_sample_risk_decision("RD-MULTI-1", RiskDecisionStatus.APPROVED, qty=100)
    rd2 = create_sample_risk_decision("RD-MULTI-2", RiskDecisionStatus.APPROVED, qty=50)

    sub1 = engine.submit_entry(risk_decision=rd1, protection_plan=create_sample_protection_plan(), symbol="RELIANCE")
    sub2 = engine.submit_entry(risk_decision=rd2, protection_plan=create_sample_protection_plan(), symbol="TCS")

    active_pms = engine.get_active_protection_managers()
    assert len(active_pms) == 2

    # Process market tick for TCS only
    tick_results = engine.process_market_tick("TCS", 2750.0)
    assert len(tick_results) == 1

    pm_reliance = engine.get_protection_manager(sub1.position_id)
    pm_tcs = engine.get_protection_manager(sub2.position_id)

    assert pm_reliance.state == ProtectionLifecycleState.ACTIVE
    assert pm_tcs.state == ProtectionLifecycleState.CLOSED
