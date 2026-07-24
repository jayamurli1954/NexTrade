# execution/state_machine.py
"""
Execution State Machine for NexTrade (Sub-Phase 3D).
Enforces valid state transition graphs for order execution lifecycle:
CREATED -> AUTHORIZED -> SUBMITTED -> PARTIALLY_FILLED -> FILLED
(or terminal failure states: REJECTED, CANCELLED, EXPIRED, UNKNOWN).
Rejects illegal state transition jumps with ValueError.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Set, List, Optional, Any

from contracts.execution import ExecutionStatus


# Valid Transition State Graph
VALID_TRANSITIONS: Dict[ExecutionStatus, Set[ExecutionStatus]] = {
    ExecutionStatus.CREATED: {
        ExecutionStatus.AUTHORIZED,
        ExecutionStatus.REJECTED
    },
    ExecutionStatus.AUTHORIZED: {
        ExecutionStatus.SUBMITTED,
        ExecutionStatus.REJECTED,
        ExecutionStatus.CANCELLED
    },
    ExecutionStatus.SUBMITTED: {
        ExecutionStatus.PARTIALLY_FILLED,
        ExecutionStatus.FILLED,
        ExecutionStatus.REJECTED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.EXPIRED,
        ExecutionStatus.UNKNOWN
    },
    ExecutionStatus.PARTIALLY_FILLED: {
        ExecutionStatus.PARTIALLY_FILLED,
        ExecutionStatus.FILLED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.EXPIRED,
        ExecutionStatus.UNKNOWN
    },
    # Terminal States (No outward transitions permitted)
    ExecutionStatus.FILLED: set(),
    ExecutionStatus.REJECTED: set(),
    ExecutionStatus.CANCELLED: set(),
    ExecutionStatus.EXPIRED: set(),
    ExecutionStatus.UNKNOWN: set(),  # Mandatory Reconciliation required
}


@dataclass
class ExecutionStateRecord:
    """Record tracking a single execution state transition."""
    execution_request_id: str
    previous_status: Optional[ExecutionStatus]
    new_status: ExecutionStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)


class ExecutionStateMachine:
    """
    State machine enforcing valid execution transitions.
    """

    def __init__(self, execution_request_id: str, initial_status: ExecutionStatus = ExecutionStatus.CREATED):
        if not execution_request_id:
            raise ValueError("execution_request_id must be a non-empty string")

        self.execution_request_id = execution_request_id
        self._current_status = initial_status
        self._history: List[ExecutionStateRecord] = []
        
        # Record initial state
        self._history.append(
            ExecutionStateRecord(
                execution_request_id=execution_request_id,
                previous_status=None,
                new_status=initial_status,
                reason="INITIAL_STATE"
            )
        )

    @property
    def current_status(self) -> ExecutionStatus:
        return self._current_status

    @property
    def is_terminal(self) -> bool:
        """Returns True if state machine is in a terminal status."""
        return len(VALID_TRANSITIONS.get(self._current_status, set())) == 0

    def transition_to(self, new_status: ExecutionStatus, reason: str = "") -> ExecutionStatus:
        """
        Transition execution state to new_status.
        Raises ValueError if transition is illegal.
        """
        if not isinstance(new_status, ExecutionStatus):
            raise ValueError(f"Expected ExecutionStatus enum, got {type(new_status).__name__}")

        if new_status == self._current_status:
            return self._current_status  # Idempotent same-state call

        allowed_next_states = VALID_TRANSITIONS.get(self._current_status, set())
        if new_status not in allowed_next_states:
            raise ValueError(
                f"Illegal state transition for execution '{self.execution_request_id}': "
                f"Cannot transition from {self._current_status.value} to {new_status.value}"
            )

        prev = self._current_status
        self._current_status = new_status
        self._history.append(
            ExecutionStateRecord(
                execution_request_id=self.execution_request_id,
                previous_status=prev,
                new_status=new_status,
                reason=reason
            )
        )
        return self._current_status

    def reconcile_to(
        self,
        new_status: ExecutionStatus,
        authority_key: str,
        reason: str = ""
    ) -> ExecutionStatus:
        """
        Invariant E29: Reconciliation Authority Boundary.
        Controlled resolution of execution state (especially UNKNOWN state) via ReconciliationEngine.
        Requires valid authority_key token. Normal components calling transition_to directly
        cannot resolve UNKNOWN state.
        """
        from execution.state_machine import RECONCILIATION_AUTHORITY_KEY
        if authority_key != RECONCILIATION_AUTHORITY_KEY:
            raise PermissionError(
                "Invariant E29 Violation: ExecutionStateMachine.reconcile_to() may only be invoked "
                "by ReconciliationEngine with exclusive authority key."
            )

        if not isinstance(new_status, ExecutionStatus):
            raise ValueError(f"Expected ExecutionStatus enum, got {type(new_status).__name__}")

        if new_status == self._current_status:
            return self._current_status

        allowed_reconciled_states = {
            ExecutionStatus.FILLED,
            ExecutionStatus.PARTIALLY_FILLED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.EXPIRED,
        }
        if new_status not in allowed_reconciled_states:
            raise ValueError(f"Cannot reconcile state to invalid target status '{new_status}'")

        prev = self._current_status
        self._current_status = new_status
        self._history.append(
            ExecutionStateRecord(
                execution_request_id=self.execution_request_id,
                previous_status=prev,
                new_status=new_status,
                reason=f"RECONCILIATION_RESOLVED: {reason}" if reason else "RECONCILIATION_RESOLVED"
            )
        )
        return self._current_status

    def get_history(self) -> List[ExecutionStateRecord]:
        """Return full transition history."""
        return list(self._history)


RECONCILIATION_AUTHORITY_KEY = "RECONCILIATION_AUTHORITY_EXCLUSIVE_KEY"
