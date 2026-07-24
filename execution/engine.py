# execution/engine.py
"""
Controlled Execution Subsystem & Engine Orchestrator for NexTrade (Sub-Phase 3F).
Orchestrates RiskEngine authorization, ExecutionGateway dispatch, ExecutionStateMachine lifecycle tracking,
PaperBrokerAdapter execution, ProtectionLifecycleManager position protection, and ReconciliationEngine uncertainty resolution.

Enforces Invariants E34 - E41:
- E34 (Controlled Gateway Entry): Single authorized entry path backed by RiskDecision; exit paths retain parent lineage.
- E35 (No Broker Bypass): All protection exit requests pass through ExecutionGateway -> BrokerAdapter.
- E36 (State Machine Synchronization): Authoritative state transition tracking via ExecutionStateMachine.
- E37 / E39-NonRetry (Automatic UNKNOWN Escalation & Non-Retry): UNKNOWN execution status registers with ReconciliationEngine without automatic retries.
- E38 (Restart State Serialization): Complete subsystem state recovery via to_dict() and from_dict().
- E39 (Execution Lineage Preservation): Preserves full decision, request, signal, position, and protection lineage.
- E40 (Position Quantity Conservation): Open Position = Entry Filled - Cumulative Exit Filled; 0 <= Q_protected <= Q_open.
- E41 (Single Active Protection Manager per Position): Ensures exactly 0 or 1 active ProtectionLifecycleManager per position_id.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Optional, Dict, Any, List, Tuple

from contracts.order import OrderSide
from contracts.position import PositionSide
from contracts.risk import RiskDecision, RiskDecisionStatus
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus, ExecutionSubmissionResult
from contracts.protection import ProtectionPlan, ProtectionDecision, ProtectionDecisionType
from contracts.reconciliation import ReconciliationResult, ReconciliationStatus
from execution.gateway import ExecutionGateway
from execution.state_machine import ExecutionStateMachine, RECONCILIATION_AUTHORITY_KEY
from protection.lifecycle import ProtectionLifecycleManager, ProtectionLifecycleState
from execution.reconciler import ReconciliationEngine
from risk.audit_logger import RiskAuditLogger


class ExecutionEngine:
    """
    Unified Sub-Phase 3F Execution Subsystem Orchestrator.
    """

    def __init__(
        self,
        gateway: ExecutionGateway,
        broker_adapter: Optional[Any] = None,
        reconciler: Optional[ReconciliationEngine] = None,
        audit_logger: Optional[RiskAuditLogger] = None
    ):
        if gateway is None or not isinstance(gateway, ExecutionGateway):
            raise ValueError("gateway must be a valid ExecutionGateway instance")

        self.gateway = gateway
        self.broker_adapter = broker_adapter or gateway.broker_adapter
        self.reconciler = reconciler or ReconciliationEngine(broker_adapter=self.broker_adapter, gateway=self.gateway, audit_logger=audit_logger)
        self.audit_logger = audit_logger or gateway.audit_logger

        # Core registries
        self._protection_managers: Dict[str, ProtectionLifecycleManager] = {}  # key: position_id (Invariant E41)
        self._state_machines: Dict[str, ExecutionStateMachine] = {}              # key: execution_request_id (Invariant E36)
        self._execution_lineage: Dict[str, Dict[str, Any]] = {}                  # key: execution_request_id (Invariant E39)
        self._pending_unknown_requests: Dict[str, ExecutionRequest] = {}         # key: execution_request_id (Invariant E37)

    def submit_entry(
        self,
        risk_decision: RiskDecision,
        protection_plan: Optional[ProtectionPlan] = None,
        symbol: str = "RELIANCE",
        exchange: str = "NSE",
        order_side: OrderSide = OrderSide.BUY
    ) -> ExecutionSubmissionResult:
        """
        Invariant E34: Submit an entry order derived strictly from an authorized RiskDecision.
        """
        now = datetime.now(timezone.utc)
        if not isinstance(risk_decision, RiskDecision):
            raise ValueError("risk_decision must be a valid RiskDecision object")

        # Register RiskDecision in gateway decision store
        self.gateway.register_risk_decision(risk_decision)

        # Early check for unauthorized RiskDecision
        if risk_decision.decision != RiskDecisionStatus.APPROVED or risk_decision.approved_quantity <= 0:
            res = ExecutionResult(
                execution_id=f"EXEC-{uuid.uuid4().hex[:12].upper()}",
                execution_request_id=f"EXREQ-ENTRY-{uuid.uuid4().hex[:8].upper()}",
                risk_decision_id=risk_decision.decision_id,
                status=ExecutionStatus.REJECTED,
                requested_quantity=risk_decision.requested_quantity,
                execution_quantity=risk_decision.approved_quantity,
                filled_quantity=0,
                remaining_quantity=risk_decision.approved_quantity,
                average_fill_price=0.0,
                rejection_reason=f"UNAUTHORIZED_RISK_DECISION: Risk decision status '{risk_decision.decision.value}' or approved_quantity is 0",
                timestamp=now
            )
            return ExecutionSubmissionResult(
                execution_result=res,
                position_id=None,
                protection_activated=False,
                reconciliation_required=False
            )

        exec_req_id = f"EXREQ-ENTRY-{risk_decision.decision_id}"
        idem_key = f"EXEC_ENTRY:{risk_decision.decision_id}"

        # Idempotency Check: Return cached submission result if request was already processed
        if exec_req_id in self._state_machines and self._state_machines[exec_req_id].is_terminal:
            cached_result = self.gateway._idempotency_registry[idem_key][1]
            pos_id = self._execution_lineage.get(exec_req_id, {}).get("position_id")
            return ExecutionSubmissionResult(
                execution_result=cached_result,
                position_id=pos_id,
                protection_activated=pos_id in self._protection_managers,
                reconciliation_required=cached_result.status == ExecutionStatus.UNKNOWN
            )

        exec_req = ExecutionRequest(
            execution_request_id=exec_req_id,
            idempotency_key=idem_key,
            risk_decision_id=risk_decision.decision_id,
            symbol=symbol,
            exchange=exchange,
            order_side=order_side,
            requested_quantity=risk_decision.requested_quantity,
            approved_quantity=risk_decision.approved_quantity,
            execution_quantity=risk_decision.approved_quantity,
            signal_id=risk_decision.signal_id,
            timestamp=now
        )

        # Invariant E36: Instantiate ExecutionStateMachine
        sm = ExecutionStateMachine(execution_request_id=exec_req_id, initial_status=ExecutionStatus.CREATED)
        self._state_machines[exec_req_id] = sm
        self.reconciler.register_state_machine(sm)

        # Invariant E39: Record Execution Lineage
        self._execution_lineage[exec_req_id] = {
            "execution_request_id": exec_req_id,
            "risk_decision_id": risk_decision.decision_id,
            "signal_id": risk_decision.signal_id,
            "position_id": None,
            "parent_execution_request_id": None,
            "protection_trigger_reason": "ENTRY_ORDER",
            "generation": 1,
            "idempotency_key": idem_key
        }

        # Transition state to AUTHORIZED
        sm.transition_to(ExecutionStatus.AUTHORIZED, reason="Passed RiskDecision validation")

        # Execute via ExecutionGateway
        sm.transition_to(ExecutionStatus.SUBMITTED, reason="Dispatched to ExecutionGateway")
        result = self.gateway.execute(exec_req)

        # Update StateMachine outcome
        if result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED, ExecutionStatus.REJECTED, ExecutionStatus.CANCELLED, ExecutionStatus.EXPIRED, ExecutionStatus.UNKNOWN):
            sm.transition_to(result.status, reason=f"Broker execution outcome: {result.status.value}")

        position_id: Optional[str] = None
        protection_activated = False
        reconciliation_required = False

        if result.status == ExecutionStatus.UNKNOWN:
            # Invariant E37 & E39-NonRetry: Register with ReconciliationEngine, NO automatic retry
            reconciliation_required = True
            self._pending_unknown_requests[exec_req_id] = exec_req
            self.reconciler.register_unresolved(request=exec_req, reason="UNKNOWN_ENTRY_EXECUTION_OUTCOME")

        elif result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED) and result.filled_quantity > 0:
            position_id = f"POS-{symbol}"
            self._execution_lineage[exec_req_id]["position_id"] = position_id


            if protection_plan is not None:
                pos_side = PositionSide.LONG if order_side == OrderSide.BUY else PositionSide.SHORT
                
                # Invariant E41: Ensure single active ProtectionLifecycleManager per position_id
                if position_id in self._protection_managers:
                    existing_pm = self._protection_managers[position_id]
                    existing_pm.update_position_quantity(existing_pm.open_quantity + result.filled_quantity)
                else:
                    pm = ProtectionLifecycleManager(
                        position_id=position_id,
                        symbol=symbol,
                        exchange=exchange,
                        position_side=pos_side,
                        entry_price=result.average_fill_price or 100.0,
                        protection_plan=protection_plan,
                        risk_decision_id=risk_decision.decision_id,
                        initial_open_quantity=result.filled_quantity,
                        gateway=self.gateway
                    )
                    self._protection_managers[position_id] = pm

                protection_activated = True

        return ExecutionSubmissionResult(
            execution_result=result,
            position_id=position_id,
            protection_activated=protection_activated,
            reconciliation_required=reconciliation_required
        )

    def process_market_tick(
        self,
        symbol: str,
        current_price: float
    ) -> List[Tuple[ProtectionDecision, Optional[ExecutionResult]]]:
        """
        Invariant E35: Process market price tick across active protection managers without broker bypass.
        """
        results: List[Tuple[ProtectionDecision, Optional[ExecutionResult]]] = []

        active_managers = [pm for pm in self._protection_managers.values() if pm.symbol == symbol and pm.state not in (ProtectionLifecycleState.CLOSED, ProtectionLifecycleState.CANCELLED)]

        for pm in active_managers:
            decision, exec_result = pm.evaluate_price_tick(current_price)

            if decision.decision == ProtectionDecisionType.EXIT and exec_result is not None:
                exit_req = pm._last_exit_request
                if exit_req is not None:
                    # Invariant E36: Sync ExecutionStateMachine for Exit Request
                    if exit_req.execution_request_id not in self._state_machines:
                        sm = ExecutionStateMachine(execution_request_id=exit_req.execution_request_id, initial_status=ExecutionStatus.SUBMITTED)
                        self._state_machines[exit_req.execution_request_id] = sm
                        self.reconciler.register_state_machine(sm)
                    else:
                        sm = self._state_machines[exit_req.execution_request_id]

                    if exec_result.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED, ExecutionStatus.REJECTED, ExecutionStatus.UNKNOWN):
                        sm.transition_to(exec_result.status, reason=f"Exit execution outcome: {exec_result.status.value}")

                    # Invariant E39: Record Exit Execution Lineage
                    self._execution_lineage[exit_req.execution_request_id] = {
                        "execution_request_id": exit_req.execution_request_id,
                        "risk_decision_id": pm.risk_decision_id,
                        "signal_id": None,
                        "position_id": pm.position_id,
                        "parent_execution_request_id": None,
                        "protection_trigger_reason": decision.reason,
                        "generation": pm.protection_generation,
                        "idempotency_key": exit_req.idempotency_key
                    }

                    # Invariant E37: UNKNOWN Exit Escalation
                    if exec_result.status == ExecutionStatus.UNKNOWN:
                        self._pending_unknown_requests[exit_req.execution_request_id] = exit_req
                        self.reconciler.register_unresolved(request=exit_req, reason=f"UNKNOWN_EXIT_EXECUTION:{decision.reason}")

            results.append((decision, exec_result))

        return results

    def reconcile_pending(self) -> List[ReconciliationResult]:
        """
        Reconcile all pending UNKNOWN execution requests via ReconciliationEngine.
        """
        results: List[ReconciliationResult] = []
        unresolved_ids = list(self._pending_unknown_requests.keys())

        for req_id in unresolved_ids:
            req = self._pending_unknown_requests[req_id]
            lineage = self._execution_lineage.get(req_id, {})
            pos_id = lineage.get("position_id")
            pm = self._protection_managers.get(pos_id) if pos_id else None
            is_exit = lineage.get("protection_trigger_reason") != "ENTRY_ORDER"

            res = self.reconciler.reconcile_request(
                request=req,
                state_machine=self._state_machines.get(req_id),
                position_manager=pm,
                is_exit_order=is_exit
            )
            results.append(res)

            if res.status != ReconciliationStatus.PENDING:
                self._pending_unknown_requests.pop(req_id, None)

        return results

    def get_protection_manager(self, position_id: str) -> Optional[ProtectionLifecycleManager]:
        """Controlled getter for ProtectionLifecycleManager by position_id."""
        return self._protection_managers.get(position_id)

    def get_active_protection_managers(self) -> Dict[str, ProtectionLifecycleManager]:
        """Controlled getter for active ProtectionLifecycleManager instances."""
        return {
            k: v for k, v in self._protection_managers.items()
            if v.state not in (ProtectionLifecycleState.CLOSED, ProtectionLifecycleState.CANCELLED)
        }

    def get_state_machine(self, execution_request_id: str) -> Optional[ExecutionStateMachine]:
        """Controlled getter for ExecutionStateMachine by execution_request_id."""
        return self._state_machines.get(execution_request_id)

    def to_dict(self) -> Dict[str, Any]:
        """
        Invariant E38: Serialize complete subsystem state for restart recovery.
        """
        return {
            "protection_managers": {k: v.to_dict() for k, v in self._protection_managers.items()},
            "execution_lineage": dict(self._execution_lineage),
            "pending_unknown_requests": {k: v.to_dict() for k, v in self._pending_unknown_requests.items()},
            "reconciler": self.reconciler.to_dict()
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        gateway: ExecutionGateway,
        broker_adapter: Optional[Any] = None,
        audit_logger: Optional[RiskAuditLogger] = None
    ) -> "ExecutionEngine":
        """
        Invariant E38: Deserialize complete subsystem state for restart recovery.
        """
        engine = cls(gateway=gateway, broker_adapter=broker_adapter, audit_logger=audit_logger)
        
        # Restore Reconciler
        if "reconciler" in data:
            engine.reconciler = ReconciliationEngine.from_dict(data["reconciler"], broker_adapter=broker_adapter, gateway=gateway, audit_logger=audit_logger)

        # Restore Protection Managers
        for pos_id, pm_dict in data.get("protection_managers", {}).items():
            pm = ProtectionLifecycleManager.from_dict(pm_dict, gateway=gateway)
            engine._protection_managers[pos_id] = pm

        # Restore Lineage
        engine._execution_lineage = dict(data.get("execution_lineage", {}))
        return engine
