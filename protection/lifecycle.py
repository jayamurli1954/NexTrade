# protection/lifecycle.py
"""
Protection Lifecycle Manager for NexTrade (Sub-Phase 3D).
Manages position-aware protection lifecycles, trailing stop progression, SL/TP triggers,
idempotent exit generation, and state recovery.
Enforces the 10 Mandatory Sub-Phase 3D Architectural Refinements:
1. No Direct Broker Bypass: Dispatches exit ExecutionRequests through ExecutionGateway.
2. Partial-Fill Position Sizing: Q_protected <= Q_open_position.
3. Deterministic SL/TP Precedence: Both boundaries crossed => AMBIGUOUS_PROTECTION_TRIGGER -> RECONCILIATION_REQUIRED.
4. Trailing Activation Lifecycle.
5. Trailing Distance vs Trailing Step separation.
6. Explicit Protection Lifecycle States (INACTIVE, ACTIVE, EXIT_PENDING, CLOSED, CANCELLED, RECONCILIATION_REQUIRED).
7. UNKNOWN Exit State & Reconciliation Integration.
8. Protection Trigger Idempotency: "PROTECTION_EXIT:{position_id}:{generation}:{trigger_reason}".
9. Explicit Protection Trigger Reasons (STOP_LOSS, TAKE_PROFIT, TRAILING_STOP, AMBIGUOUS_PROTECTION_TRIGGER).
10. Restart State Recovery via to_dict() and from_dict().
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Optional, Dict, Any, Tuple, List

from contracts.position import PositionSide
from contracts.order import OrderSide
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from contracts.protection import (
    ProtectionPlan,
    TrailingDistanceType,
    TrailingStopState,
    ProtectionDecision,
    ProtectionDecisionType,
    ProtectionAdjustmentEvent,
)


class ProtectionLifecycleState(str, Enum):
    """Protection lifecycle state."""
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ProtectionTriggerReason(str, Enum):
    """Reason for protection exit trigger."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL_EXIT = "MANUAL_EXIT"
    RISK_EXIT = "RISK_EXIT"
    AMBIGUOUS_PROTECTION_TRIGGER = "AMBIGUOUS_PROTECTION_TRIGGER"


class ProtectionLifecycleManager:
    """
    Position-Aware Protection Lifecycle Manager.
    """

    def __init__(
        self,
        position_id: str,
        symbol: str,
        exchange: str,
        position_side: PositionSide,
        entry_price: float,
        protection_plan: ProtectionPlan,
        risk_decision_id: str,
        initial_open_quantity: int = 0,
        gateway: Optional[Any] = None
    ):
        self.position_id = position_id
        self.symbol = symbol
        self.exchange = exchange
        self.position_side = position_side
        self.entry_price = entry_price
        self.protection_plan = protection_plan
        self.risk_decision_id = risk_decision_id
        self.gateway = gateway

        self.open_quantity = initial_open_quantity
        self.state = ProtectionLifecycleState.ACTIVE if initial_open_quantity > 0 else ProtectionLifecycleState.INACTIVE
        self.protection_generation = 1
        self._last_exit_request: Optional[ExecutionRequest] = None
        self._last_exit_result: Optional[ExecutionResult] = None
        self._adjustment_history: List[ProtectionAdjustmentEvent] = []

        # Initialize Trailing Stop State if trailing is enabled
        self.trailing_state: Optional[TrailingStopState] = None
        if self.protection_plan.trailing_enabled:
            init_sl = self.protection_plan.initial_stop_loss or (
                self.entry_price - (self.protection_plan.trailing_distance or 10.0)
                if self.position_side == PositionSide.LONG
                else self.entry_price + (self.protection_plan.trailing_distance or 10.0)
            )
            self.trailing_state = TrailingStopState(
                position_side=self.position_side,
                entry_price=self.entry_price,
                current_stop_loss=init_sl,
                trailing_distance=self.protection_plan.trailing_distance or 10.0,
                trailing_distance_type=self.protection_plan.trailing_distance_type,
                trailing_step=self.protection_plan.trailing_step or 1.0,
                highest_favorable_price=self.entry_price,
                last_reference_price=self.entry_price,
                is_active=True
            )

    def update_position_quantity(self, new_open_quantity: int) -> None:
        """
        Refinement 2: Dynamic position-aware protection quantity update.
        """
        if new_open_quantity < 0:
            raise ValueError(f"open_quantity must be non-negative, got {new_open_quantity}")

        self.open_quantity = new_open_quantity
        if self.open_quantity == 0 and self.state not in (ProtectionLifecycleState.CLOSED, ProtectionLifecycleState.CANCELLED):
            self.state = ProtectionLifecycleState.CLOSED

    def evaluate_price_tick(self, current_market_price: float) -> Tuple[ProtectionDecision, Optional[ExecutionResult]]:
        """
        Evaluate market price tick against active protection plan and state.
        Returns (ProtectionDecision, Optional[ExecutionResult]).
        """
        now = datetime.now(timezone.utc)

        # Refinement 6: CLOSED / INACTIVE / RECONCILIATION_REQUIRED state check
        if self.state in (ProtectionLifecycleState.CLOSED, ProtectionLifecycleState.CANCELLED, ProtectionLifecycleState.INACTIVE):
            return ProtectionDecision(
                decision=ProtectionDecisionType.NO_ACTION,
                position_id=self.position_id,
                symbol=self.symbol,
                position_side=self.position_side,
                trigger_price=current_market_price,
                reason="LIFECYCLE_INACTIVE_OR_CLOSED",
                timestamp=now
            ), None

        if self.state == ProtectionLifecycleState.RECONCILIATION_REQUIRED:
            return ProtectionDecision(
                decision=ProtectionDecisionType.NO_ACTION,
                position_id=self.position_id,
                symbol=self.symbol,
                position_side=self.position_side,
                trigger_price=current_market_price,
                reason="RECONCILIATION_REQUIRED: Pending ambiguous exit outcome",
                timestamp=now
            ), self._last_exit_result

        # Refinement 8: Pending exit idempotency check
        if self.state == ProtectionLifecycleState.EXIT_PENDING:
            return ProtectionDecision(
                decision=ProtectionDecisionType.NO_ACTION,
                position_id=self.position_id,
                symbol=self.symbol,
                position_side=self.position_side,
                trigger_price=current_market_price,
                reason="EXIT_PENDING: Exit request currently in-flight",
                timestamp=now
            ), self._last_exit_result

        # Determine SL and TP breach conditions
        sl_breached = False
        tp_breached = False

        effective_sl = (
            self.trailing_state.current_stop_loss
            if self.trailing_state is not None
            else self.protection_plan.initial_stop_loss
        )
        effective_tp = self.protection_plan.initial_take_profit

        if self.position_side == PositionSide.LONG:
            if effective_sl is not None and current_market_price <= effective_sl:
                sl_breached = True
            if effective_tp is not None and current_market_price >= effective_tp:
                tp_breached = True
        elif self.position_side == PositionSide.SHORT:
            if effective_sl is not None and current_market_price >= effective_sl:
                sl_breached = True
            if effective_tp is not None and current_market_price <= effective_tp:
                tp_breached = True

        # Refinement 3: Ambiguous SL/TP Breach Precedence Check
        if sl_breached and tp_breached:
            self.state = ProtectionLifecycleState.RECONCILIATION_REQUIRED
            dec = ProtectionDecision(
                decision=ProtectionDecisionType.EXIT,
                position_id=self.position_id,
                symbol=self.symbol,
                position_side=self.position_side,
                trigger_price=current_market_price,
                reason=ProtectionTriggerReason.AMBIGUOUS_PROTECTION_TRIGGER.value,
                timestamp=now
            )
            return dec, None

        # Exit Trigger Processing
        trigger_reason: Optional[ProtectionTriggerReason] = None
        if sl_breached:
            trigger_reason = ProtectionTriggerReason.TRAILING_STOP if self.protection_plan.trailing_enabled else ProtectionTriggerReason.STOP_LOSS
        elif tp_breached:
            trigger_reason = ProtectionTriggerReason.TAKE_PROFIT

        if trigger_reason is not None:
            # Refinement 1: Construct Exit ExecutionRequest -> Dispatch to ExecutionGateway
            exit_side = OrderSide.SELL if self.position_side == PositionSide.LONG else OrderSide.BUY
            exit_req_id = f"EXREQ-EXIT-{uuid.uuid4().hex[:8].upper()}"
            
            # Refinement 8: Protection trigger idempotency key
            idem_key = f"PROTECTION_EXIT:{self.position_id}:{self.protection_generation}:{trigger_reason.value}"

            exit_req = ExecutionRequest(
                execution_request_id=exit_req_id,
                idempotency_key=idem_key,
                risk_decision_id=self.risk_decision_id,
                symbol=self.symbol,
                exchange=self.exchange,
                order_side=exit_side,
                requested_quantity=self.open_quantity,
                approved_quantity=self.open_quantity,
                execution_quantity=self.open_quantity,
                timestamp=now
            )

            self._last_exit_request = exit_req
            self.state = ProtectionLifecycleState.EXIT_PENDING

            dec = ProtectionDecision(
                decision=ProtectionDecisionType.EXIT,
                position_id=self.position_id,
                symbol=self.symbol,
                position_side=self.position_side,
                trigger_price=current_market_price,
                current_stop_loss=effective_sl,
                take_profit_price=effective_tp,
                reason=trigger_reason.value,
                timestamp=now
            )

            exec_result: Optional[ExecutionResult] = None
            if self.gateway is not None and hasattr(self.gateway, "execute"):
                exec_result = self.gateway.execute(exit_req)
                self._last_exit_result = exec_result

                # Refinement 7: UNKNOWN Exit Handling & Reconciliation Integration
                if exec_result.status == ExecutionStatus.UNKNOWN:
                    self.state = ProtectionLifecycleState.RECONCILIATION_REQUIRED
                elif exec_result.status in (ExecutionStatus.FILLED, ExecutionStatus.SUBMITTED):
                    self.open_quantity -= exec_result.filled_quantity
                    if self.open_quantity == 0:
                        self.state = ProtectionLifecycleState.CLOSED
                elif exec_result.status == ExecutionStatus.REJECTED:
                    # Deterministic failure -> Return to ACTIVE state
                    self.state = ProtectionLifecycleState.ACTIVE

            return dec, exec_result

        # Evaluate Trailing Stop Progression (Refinement 4 & 5)
        if self.trailing_state is not None:
            updated, new_trailing = self.trailing_state.calculate_update(current_market_price)
            if updated:
                prev_sl = self.trailing_state.current_stop_loss
                self.trailing_state = new_trailing
                
                # Emit ProtectionAdjustmentEvent (Refinement 9 & Invariant E23)
                adj_event = ProtectionAdjustmentEvent(
                    event_id=f"PAE-{uuid.uuid4().hex[:8].upper()}",
                    execution_request_id="N/A",
                    risk_decision_id=self.risk_decision_id,
                    symbol=self.symbol,
                    position_side=self.position_side,
                    previous_stop_loss=prev_sl,
                    new_stop_loss=new_trailing.current_stop_loss,
                    trigger_market_price=current_market_price,
                    reason="TRAILING_STEP_UPDATED",
                    timestamp=now
                )
                self._adjustment_history.append(adj_event)

                dec = ProtectionDecision(
                    decision=ProtectionDecisionType.UPDATE_TRAILING_STOP,
                    position_id=self.position_id,
                    symbol=self.symbol,
                    position_side=self.position_side,
                    trigger_price=current_market_price,
                    current_stop_loss=prev_sl,
                    new_stop_loss=new_trailing.current_stop_loss,
                    reason="TRAILING_STEP_UPDATED",
                    timestamp=now
                )
                return dec, None

        return ProtectionDecision(
            decision=ProtectionDecisionType.NO_ACTION,
            position_id=self.position_id,
            symbol=self.symbol,
            position_side=self.position_side,
            trigger_price=current_market_price,
            reason="NO_ACTION",
            timestamp=now
        ), None

    def to_dict(self) -> Dict[str, Any]:
        """Refinement 10: Serialize state for restart recovery."""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "position_side": self.position_side.value if isinstance(self.position_side, Enum) else str(self.position_side),
            "entry_price": self.entry_price,
            "risk_decision_id": self.risk_decision_id,
            "open_quantity": self.open_quantity,
            "state": self.state.value if isinstance(self.state, Enum) else str(self.state),
            "protection_plan": self.protection_plan.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], gateway: Optional[Any] = None) -> "ProtectionLifecycleManager":
        """Refinement 10: Deserialize state for restart recovery."""
        plan_dict = data["protection_plan"]
        plan = ProtectionPlan(
            position_side=PositionSide(plan_dict["position_side"]),
            entry_price=plan_dict["entry_price"],
            initial_stop_loss=plan_dict.get("initial_stop_loss"),
            initial_take_profit=plan_dict.get("initial_take_profit"),
            trailing_enabled=plan_dict.get("trailing_enabled", False),
            trailing_distance=plan_dict.get("trailing_distance"),
            trailing_distance_type=TrailingDistanceType(plan_dict.get("trailing_distance_type", "ABSOLUTE")),
            trailing_step=plan_dict.get("trailing_step"),
            trailing_activation_price=plan_dict.get("trailing_activation_price")
        )

        mgr = cls(
            position_id=data["position_id"],
            symbol=data["symbol"],
            exchange=data["exchange"],
            position_side=PositionSide(data["position_side"]),
            entry_price=data["entry_price"],
            protection_plan=plan,
            risk_decision_id=data["risk_decision_id"],
            initial_open_quantity=data.get("open_quantity", 0),
            gateway=gateway
        )
        mgr.state = ProtectionLifecycleState(data.get("state", "ACTIVE"))
        return mgr
