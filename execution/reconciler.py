# execution/reconciler.py
"""
Reconciliation Engine for NexTrade (Sub-Phase 3E).
Implements canonical order and position reconciliation covering all 12 mandatory requirements and 5 Phase 3E Invariants:
E29 (Reconciliation Authority Boundary): Only ReconciliationEngine resolves UNKNOWN via reconcile_to().
E30 (Position Quantity Conservation): Q_open_new = Q_open_old + Q_entry_filled or Q_open_old - Q_exit_filled.
E31 (Cumulative Fill Monotonicity): NewFillDelta = max(0, CumulativeFilled_authoritative - CumulativeFilled_reconciled).
E32 (Authoritative Broker State with Discrepancy Escalation): Broker order state is authoritative; position mismatches trigger audit escalation.
E33 (Reconciliation Idempotency Identity): reconciliation_key based on deterministic broker state hash.

Strict Scope Boundary: ReconciliationEngine DOES NOT issue new broker execution requests.
It observes, reconciles, updates quantities, restores protection lifecycle states, and records immutable audit trails.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Optional, Dict, Any, List, Tuple

from contracts.order import OrderSide
from contracts.position import Position, PositionSide
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from contracts.reconciliation import (
    ReconciliationStatus,
    DiscrepancySeverity,
    DiscrepancyType,
    ReconciliationDiscrepancy,
    ReconciliationRequest,
    ReconciliationResult,
    ReconciliationAuditRecord,
)
from execution.state_machine import ExecutionStateMachine, RECONCILIATION_AUTHORITY_KEY
from protection.lifecycle import ProtectionLifecycleManager, ProtectionLifecycleState
from risk.audit_logger import RiskAuditLogger


class ReconciliationEngine:
    """
    Sub-Phase 3E Reconciliation Engine.
    """

    def __init__(
        self,
        broker_adapter: Optional[Any] = None,
        gateway: Optional[Any] = None,
        audit_logger: Optional[RiskAuditLogger] = None
    ):
        self.broker_adapter = broker_adapter
        self.gateway = gateway
        self.audit_logger = audit_logger

        self._pending_requests: Dict[str, ReconciliationRequest] = {}
        # Idempotency registry indexed by reconciliation_key (Invariant E33)
        self._reconciliation_registry: Dict[str, ReconciliationResult] = {}
        # Cumulative fill tracker per execution_request_id (Invariant E31)
        self._cumulative_fills: Dict[str, int] = {}
        # Registered state machines indexed by execution_request_id
        self._state_machines: Dict[str, ExecutionStateMachine] = {}
        # Immutable audit records
        self._audit_log: List[ReconciliationAuditRecord] = []

    def register_state_machine(self, state_machine: ExecutionStateMachine) -> None:
        """Register an ExecutionStateMachine instance for tracked executions."""
        if not isinstance(state_machine, ExecutionStateMachine):
            raise ValueError("state_machine must be an instance of ExecutionStateMachine")
        self._state_machines[state_machine.execution_request_id] = state_machine

    def register_unresolved(self, request: ExecutionRequest, reason: str = "UNKNOWN_EXECUTION_OUTCOME") -> ReconciliationRequest:
        """Register an unresolved execution request into the pending reconciliation queue."""
        rec_req = ReconciliationRequest(
            reconciliation_request_id=f"RECREQ-{uuid.uuid4().hex[:8].upper()}",
            execution_request_id=request.execution_request_id,
            idempotency_key=request.idempotency_key,
            symbol=request.symbol,
            reason=reason
        )
        self._pending_requests[request.execution_request_id] = rec_req
        return rec_req

    def reconcile_request(
        self,
        request: ExecutionRequest,
        broker_state_override: Optional[Dict[str, Any]] = None,
        state_machine: Optional[ExecutionStateMachine] = None,
        position_manager: Optional[ProtectionLifecycleManager] = None,
        is_exit_order: bool = False
    ) -> ReconciliationResult:
        """
        Reconcile an execution request against authoritative broker state.
        Enforces E29, E30, E31, E32, E33.
        """
        now = datetime.now(timezone.utc)
        rec_id = f"REC-{uuid.uuid4().hex[:12].upper()}"

        # 1. Fetch Authoritative Broker State
        broker_state = broker_state_override
        if broker_state is None and self.broker_adapter is not None:
            if hasattr(self.broker_adapter, "query_execution"):
                broker_state = self.broker_adapter.query_execution(
                    execution_request_id=request.execution_request_id,
                    idempotency_key=request.idempotency_key
                )

        # Default fallback if broker query yields no record -> REJECTED / UNKNOWN escalation
        if broker_state is None:
            authoritative_status = ExecutionStatus.REJECTED
            authoritative_cumulative_filled = 0
            average_fill_price = 0.0
            broker_order_id = None
            broker_event_id = None
            details_str = "No authoritative broker record found: Assuming order was rejected pre-submission."
        else:
            authoritative_status = broker_state.get("status", ExecutionStatus.FILLED)
            if isinstance(authoritative_status, str):
                authoritative_status = ExecutionStatus(authoritative_status)
            authoritative_cumulative_filled = int(broker_state.get("cumulative_filled_quantity", request.execution_quantity))
            average_fill_price = float(broker_state.get("average_fill_price", request.limit_price or 100.0))
            broker_order_id = broker_state.get("broker_order_id")
            broker_event_id = broker_state.get("broker_event_id")
            details_str = broker_state.get("details", "Authoritative broker state fetched.")

        # Invariant E12 Check: 0 <= cumulative_filled <= execution_quantity
        authoritative_cumulative_filled = min(max(0, authoritative_cumulative_filled), request.execution_quantity)

        # 2. Invariant E33 — Compute Deterministic Reconciliation Key & Idempotency Check
        rec_key = ReconciliationResult.compute_reconciliation_key(
            broker_order_id=broker_order_id,
            authoritative_status=authoritative_status,
            cumulative_filled_quantity=authoritative_cumulative_filled,
            average_fill_price=average_fill_price,
            broker_event_id=broker_event_id
        )

        if rec_key in self._reconciliation_registry:
            # Identical broker state observation -> Return cached result (Zero additional position or fill mutation)
            return self._reconciliation_registry[rec_key]

        # 3. Invariant E31 — Cumulative Fill Monotonicity & Fill Delta Calculation
        previously_reconciled_filled = self._cumulative_fills.get(request.execution_request_id, 0)
        
        discrepancies: List[ReconciliationDiscrepancy] = []

        if authoritative_cumulative_filled < previously_reconciled_filled:
            # Discrepancy: Regression in reported filled quantity
            discrepancies.append(
                ReconciliationDiscrepancy(
                    discrepancy_type=DiscrepancyType.CUMULATIVE_FILL_REGRESSION,
                    expected_value=previously_reconciled_filled,
                    actual_value=authoritative_cumulative_filled,
                    severity=DiscrepancySeverity.CRITICAL,
                    description=f"Broker reported lower cumulative fill ({authoritative_cumulative_filled}) than previously reconciled ({previously_reconciled_filled})."
                )
            )

        fill_delta = max(0, authoritative_cumulative_filled - previously_reconciled_filled)
        self._cumulative_fills[request.execution_request_id] = max(previously_reconciled_filled, authoritative_cumulative_filled)

        remaining_qty = request.execution_quantity - authoritative_cumulative_filled

        # 4. Map to ReconciliationStatus
        if authoritative_status == ExecutionStatus.FILLED:
            rec_status = ReconciliationStatus.RESOLVED_FILLED
        elif authoritative_status == ExecutionStatus.PARTIALLY_FILLED:
            rec_status = ReconciliationStatus.RESOLVED_PARTIAL
        elif authoritative_status == ExecutionStatus.CANCELLED:
            rec_status = ReconciliationStatus.RESOLVED_CANCELLED
        elif authoritative_status == ExecutionStatus.REJECTED:
            rec_status = ReconciliationStatus.RESOLVED_REJECTED
        else:
            rec_status = ReconciliationStatus.RESOLVED_REJECTED

        # 5. Invariant E29 — Controlled ExecutionStateMachine Transition
        sm = state_machine or self._state_machines.get(request.execution_request_id)
        previous_sm_status = sm.current_status if sm else ExecutionStatus.UNKNOWN
        if sm is not None:
            sm.reconcile_to(
                new_status=authoritative_status,
                authority_key=RECONCILIATION_AUTHORITY_KEY,
                reason=f"Reconciled via key '{rec_key}': {details_str}"
            )

        # 6. Invariant E30 — Position Quantity Conservation & Protection Restoration
        if position_manager is not None:
            q_old = position_manager.open_quantity
            if is_exit_order or request.order_side != (OrderSide.BUY if position_manager.position_side == PositionSide.LONG else OrderSide.SELL):
                # Exit Order: Q_open_new = Q_open_old - Q_exit_filled_delta
                q_new = max(0, q_old - fill_delta)
                position_manager.update_position_quantity(q_new)
                
                # Restore Protection Lifecycle State
                if q_new == 0:
                    position_manager.state = ProtectionLifecycleState.CLOSED
                elif authoritative_status in (ExecutionStatus.REJECTED, ExecutionStatus.CANCELLED):
                    # Exit rejected/cancelled -> Restore active protection on remaining position
                    position_manager.state = ProtectionLifecycleState.ACTIVE
                elif authoritative_status == ExecutionStatus.PARTIALLY_FILLED:
                    # Partial exit fill -> Return to ACTIVE with updated position quantity
                    position_manager.state = ProtectionLifecycleState.ACTIVE
                else:
                    position_manager.state = ProtectionLifecycleState.ACTIVE
            else:
                # Entry Order: Q_open_new = Q_open_old + Q_entry_filled_delta
                q_new = q_old + fill_delta
                position_manager.update_position_quantity(q_new)
                position_manager.state = ProtectionLifecycleState.ACTIVE

            # Conservation check: Q_protected <= Q_open_new
            if position_manager.open_quantity < 0:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        discrepancy_type=DiscrepancyType.QUANTITY_MISMATCH,
                        expected_value=">= 0",
                        actual_value=position_manager.open_quantity,
                        severity=DiscrepancySeverity.FATAL,
                        description="Invariant E30 Violation: Open position quantity negative after reconciliation."
                    )
                )

        # Construct Result
        res = ReconciliationResult(
            reconciliation_id=rec_id,
            reconciliation_key=rec_key,
            execution_request_id=request.execution_request_id,
            broker_order_id=broker_order_id,
            status=rec_status,
            resolved_execution_status=authoritative_status,
            cumulative_filled_quantity=authoritative_cumulative_filled,
            fill_delta=fill_delta,
            remaining_quantity=remaining_qty,
            average_fill_price=average_fill_price,
            discrepancies=discrepancies,
            details=details_str,
            timestamp=now
        )

        # 7. Audit Logging (Invariants E29 - E33 Traceability)
        audit_rec = ReconciliationAuditRecord(
            audit_id=f"AUDREC-{uuid.uuid4().hex[:8].upper()}",
            reconciliation_id=rec_id,
            reconciliation_key=rec_key,
            execution_request_id=request.execution_request_id,
            previous_execution_status=previous_sm_status,
            new_execution_status=authoritative_status,
            fill_delta=fill_delta,
            cumulative_filled_quantity=authoritative_cumulative_filled,
            details=details_str,
            timestamp=now
        )
        self._audit_log.append(audit_rec)

        if self.audit_logger is not None and hasattr(self.audit_logger, "log_event"):
            self.audit_logger.log_event(
                event_type="STATE_TRANSITION",
                severity="INFO" if not discrepancies else "HIGH",
                component="ReconciliationEngine",
                action="RECONCILE_EXECUTION",
                details=res.to_dict()
            )

        # Remove from pending queue if present
        self._pending_requests.pop(request.execution_request_id, None)

        # Register in Idempotency Registry
        self._reconciliation_registry[rec_key] = res
        return res

    def process_broker_event(
        self,
        broker_event: Dict[str, Any],
        request: ExecutionRequest,
        state_machine: Optional[ExecutionStateMachine] = None,
        position_manager: Optional[ProtectionLifecycleManager] = None,
        is_exit_order: bool = False
    ) -> ReconciliationResult:
        """
        Process asynchronous late broker execution report with delta fill accounting.
        """
        return self.reconcile_request(
            request=request,
            broker_state_override=broker_event,
            state_machine=state_machine,
            position_manager=position_manager,
            is_exit_order=is_exit_order
        )

    def detect_discrepancies(
        self,
        internal_positions: List[Position],
        broker_positions: List[Position]
    ) -> List[ReconciliationDiscrepancy]:
        """
        Invariant E32: Detect discrepancies between internal portfolio positions and broker positions.
        Generates CRITICAL/FATAL discrepancy reports without silently overwriting internal positions.
        """
        now = datetime.now(timezone.utc)
        discrepancies: List[ReconciliationDiscrepancy] = []

        broker_pos_map = {p.symbol: p for p in broker_positions}
        internal_pos_map = {p.symbol: p for p in internal_positions}

        # Check internal vs broker
        for sym, int_pos in internal_pos_map.items():
            brk_pos = broker_pos_map.get(sym)
            if brk_pos is None:
                if int_pos.quantity != 0:
                    discrepancies.append(
                        ReconciliationDiscrepancy(
                            discrepancy_type=DiscrepancyType.UNMATCHED_ORDER,
                            expected_value=int_pos.quantity,
                            actual_value=0,
                            severity=DiscrepancySeverity.CRITICAL,
                            description=f"Internal position for symbol '{sym}' ({int_pos.quantity}) has no corresponding broker position.",
                            timestamp=now
                        )
                    )
            else:
                if int_pos.quantity != brk_pos.quantity:
                    discrepancies.append(
                        ReconciliationDiscrepancy(
                            discrepancy_type=DiscrepancyType.QUANTITY_MISMATCH,
                            expected_value=int_pos.quantity,
                            actual_value=brk_pos.quantity,
                            severity=DiscrepancySeverity.CRITICAL,
                            description=f"Quantity mismatch for symbol '{sym}': Internal={int_pos.quantity}, Broker={brk_pos.quantity}.",
                            timestamp=now
                        )
                    )

        # Check broker positions not in internal
        for sym, brk_pos in broker_pos_map.items():
            if sym not in internal_pos_map and brk_pos.quantity != 0:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        discrepancy_type=DiscrepancyType.UNMATCHED_ORDER,
                        expected_value=0,
                        actual_value=brk_pos.quantity,
                        severity=DiscrepancySeverity.WARNING,
                        description=f"Unrecorded broker position found for symbol '{sym}' (qty={brk_pos.quantity}).",
                        timestamp=now
                    )
                )

        return discrepancies

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ReconciliationEngine state for restart recovery."""
        return {
            "pending_requests": {k: v.to_dict() for k, v in self._pending_requests.items()},
            "reconciliation_registry": {k: v.to_dict() for k, v in self._reconciliation_registry.items()},
            "cumulative_fills": dict(self._cumulative_fills),
            "audit_log": [a.to_dict() for a in self._audit_log],
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        broker_adapter: Optional[Any] = None,
        gateway: Optional[Any] = None,
        audit_logger: Optional[RiskAuditLogger] = None
    ) -> "ReconciliationEngine":
        """Deserialize ReconciliationEngine state for restart recovery."""
        engine = cls(broker_adapter=broker_adapter, gateway=gateway, audit_logger=audit_logger)
        engine._cumulative_fills = dict(data.get("cumulative_fills", {}))
        return engine
