# execution/gateway.py
"""
Canonical Execution Gateway for NexTrade (Sub-Phase 3B).
Acts as the sole application-level entry point for execution requests.
Delegates authorization evaluation directly to ExecutionAuthorizationGate (Phase 2H)
and enforces Decision Binding, Quantity Integrity (Q_exec <= Q_approved), and
Invariant E10 (Idempotency Intent Binding).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple, Any

from contracts.risk import RiskDecision, RiskDecisionStatus
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from risk.execution_gate import ExecutionAuthorizationGate
from risk.audit_logger import RiskAuditLogger, AuditHealthStatus


class ExecutionGateway:
    """
    Execution Firewall Gateway.
    Bridge between authorized RiskDecisions and downstream BrokerAdapters.
    """

    def __init__(
        self,
        audit_logger: Optional[RiskAuditLogger] = None,
        broker_adapter: Optional[Any] = None
    ):
        self.audit_logger = audit_logger
        self.broker_adapter = broker_adapter
        self._decision_store: Dict[str, RiskDecision] = {}
        # Idempotency Registry mapping idempotency_key -> (ExecutionRequest, ExecutionResult)
        self._idempotency_registry: Dict[str, Tuple[ExecutionRequest, ExecutionResult]] = {}

    def register_risk_decision(self, decision: RiskDecision) -> None:
        """Register an authoritative RiskDecision produced by RiskEngine."""
        if not isinstance(decision, RiskDecision):
            raise ValueError("decision must be a valid RiskDecision object")
        self._decision_store[decision.decision_id] = decision

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Execute an ExecutionRequest safely.
        
        Verification Steps:
        1. Invariant E10: Idempotency Intent Binding Check.
        2. Resolve Authoritative RiskDecision by risk_decision_id.
        3. Authoritative Quantity Check: Q_exec <= authoritative_RiskDecision.approved_quantity.
        4. Delegate Authorization to ExecutionAuthorizationGate.can_execute(decision, audit_health).
        5. Submit to downstream BrokerAdapter if authorized; return ExecutionResult.
        """
        now = datetime.now(timezone.utc)
        exec_id = f"EXEC-{uuid.uuid4().hex[:12].upper()}"

        # 1. Invariant E10 — Idempotency Intent Binding Check
        if request.idempotency_key in self._idempotency_registry:
            original_req, cached_res = self._idempotency_registry[request.idempotency_key]
            
            # Check for Intent Conflict
            if (original_req.execution_request_id != request.execution_request_id or
                original_req.risk_decision_id != request.risk_decision_id or
                original_req.symbol != request.symbol or
                original_req.order_side != request.order_side or
                original_req.execution_quantity != request.execution_quantity):
                
                # Conflicting Intent -> Reject immediately
                return ExecutionResult(
                    execution_id=exec_id,
                    execution_request_id=request.execution_request_id,
                    risk_decision_id=request.risk_decision_id,
                    status=ExecutionStatus.REJECTED,
                    requested_quantity=request.requested_quantity,
                    execution_quantity=request.execution_quantity,
                    filled_quantity=0,
                    remaining_quantity=request.execution_quantity,
                    average_fill_price=0.0,
                    rejection_reason="IDEMPOTENCY_CONFLICT: Idempotency key reused with conflicting execution intent",
                    timestamp=now
                )
            
            # Identical Request -> Return cached result
            return cached_res

        # Helper for rejection responses
        def reject(reason: str) -> ExecutionResult:
            res = ExecutionResult(
                execution_id=exec_id,
                execution_request_id=request.execution_request_id,
                risk_decision_id=request.risk_decision_id,
                status=ExecutionStatus.REJECTED,
                requested_quantity=request.requested_quantity,
                execution_quantity=request.execution_quantity,
                filled_quantity=0,
                remaining_quantity=request.execution_quantity,
                average_fill_price=0.0,
                rejection_reason=reason,
                timestamp=now
            )
            self._idempotency_registry[request.idempotency_key] = (request, res)
            return res

        # 2. Resolve Authoritative RiskDecision
        authoritative_decision = self._decision_store.get(request.risk_decision_id)
        if authoritative_decision is None:
            return reject(f"UNKNOWN_RISK_DECISION: No registered RiskDecision found for ID '{request.risk_decision_id}'")

        # 3. Authoritative Quantity Check: Q_exec <= authoritative_RiskDecision.approved_quantity
        if request.execution_quantity > authoritative_decision.approved_quantity:
            return reject(
                f"QUANTITY_EXCEEDED: Requested execution_quantity ({request.execution_quantity}) "
                f"exceeds authoritative approved_quantity ({authoritative_decision.approved_quantity})"
            )

        # 4. Delegate Authorization directly to ExecutionAuthorizationGate (Phase 2H)
        audit_health: Optional[AuditHealthStatus] = None
        if self.audit_logger is not None:
            audit_health = self.audit_logger.health()

        is_authorized = ExecutionAuthorizationGate.can_execute(
            decision=authoritative_decision,
            audit_health=audit_health
        )

        if not is_authorized:
            return reject(
                f"EXECUTION_GATE_DENIED: ExecutionAuthorizationGate denied execution for decision '{authoritative_decision.decision_id}'"
            )

        # 5. Execute via BrokerAdapter (if configured) or Default Paper Stub
        if self.broker_adapter is not None and hasattr(self.broker_adapter, "execute_order"):
            try:
                result = self.broker_adapter.execute_order(request)
            except Exception as e:
                result = reject(f"BROKER_ADAPTER_ERROR: Broker adapter execution failed: {str(e)}")
        else:
            # Default Sandbox/Paper Stub Execution Result
            result = ExecutionResult(
                execution_id=exec_id,
                execution_request_id=request.execution_request_id,
                risk_decision_id=request.risk_decision_id,
                status=ExecutionStatus.SUBMITTED,
                requested_quantity=request.requested_quantity,
                execution_quantity=request.execution_quantity,
                filled_quantity=0,
                remaining_quantity=request.execution_quantity,
                average_fill_price=0.0,
                broker_order_id=f"PAPER-{exec_id}",
                timestamp=now
            )

        # Register in Idempotency Registry
        self._idempotency_registry[request.idempotency_key] = (request, result)
        return result
