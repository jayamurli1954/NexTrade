# events/state_integrator.py
"""
State Machine & Position Integrator for NexTrade (Sub-Phase 4E).
Translates canonical execution events into validated state machine transitions via
ExecutionStateMachine.transition_to() or reconcile_to(). Zero direct state mutations or order dispatches.
"""
from typing import Dict, Any, Optional

from contracts.execution import ExecutionStatus
from contracts.event_contracts import CanonicalEvent, StreamType, EventType
from execution.state_machine import ExecutionStateMachine


class StateIntegrator:
    """
    Subscribes to execution events and drives state updates strictly through ExecutionStateMachine.
    """

    def __init__(self, state_machine_registry: Optional[Dict[str, ExecutionStateMachine]] = None):
        self._state_machines: Dict[str, ExecutionStateMachine] = state_machine_registry or {}

    def register_state_machine(self, execution_id: str, state_machine: ExecutionStateMachine) -> None:
        """Registers an ExecutionStateMachine instance for state integration."""
        self._state_machines[execution_id] = state_machine

    def handle_event(self, event: CanonicalEvent) -> bool:
        """
        Handles an incoming CanonicalEvent.
        Routes execution events to ExecutionStateMachine.transition_to() or reconcile_to().
        """
        if event.stream_type != StreamType.EXECUTION:
            return False

        exec_id = event.payload.get("nextrade_execution_id") or event.payload.get("broker_order_id")
        if not exec_id:
            return False

        sm = self._state_machines.get(exec_id)
        if sm is None:
            return False

        # Event type to ExecutionStatus mapping
        status_map = {
            EventType.ORDER_SUBMITTED: ExecutionStatus.SUBMITTED,
            EventType.ORDER_FILLED: ExecutionStatus.FILLED,
            EventType.ORDER_PARTIALLY_FILLED: ExecutionStatus.PARTIALLY_FILLED,
            EventType.ORDER_CANCELLED: ExecutionStatus.CANCELLED,
            EventType.ORDER_REJECTED: ExecutionStatus.REJECTED,
        }

        target_status = status_map.get(event.event_type)
        if target_status is None:
            return False

        try:
            # Enforce validated transition pathway (Invariant E1–E41)
            sm.transition_to(target_status)
            return True
        except ValueError:
            # Invalid transition attempt -> Route through reconcile_to if authority key is present
            reconcile_key = event.payload.get("reconciliation_authority_key")
            if reconcile_key:
                sm.reconcile_to(target_status, authority_key=reconcile_key)
                return True
            return False
