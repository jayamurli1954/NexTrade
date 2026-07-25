# staging/circuit_breaker.py
"""
Circuit Breakers & Emergency Kill Switch Manager for NexTrade (Sub-Phase 4J).
Implements dominant kill switch hierarchy (Invariant 4J-P12), HARD_HALT vs REDUCE_ONLY,
and fail-closed state uncertainty enforcement (Invariant 4J-P11).
"""
import threading
from enum import Enum
from typing import Optional, Dict, Any, Tuple


class CircuitState(str, Enum):
    NORMAL = "NORMAL"
    REDUCE_ONLY = "REDUCE_ONLY"
    HARD_HALT = "HARD_HALT"


class CircuitBreakerManager:
    """
    Thread-safe circuit breaker and emergency kill switch manager.
    Enforces dominant hierarchy: KILL_SWITCH > HARD_HALT > RECONCILIATION_FAILURE > CIRCUIT_BREAKER.
    """

    def __init__(self):
        self._state = CircuitState.NORMAL
        self._lock = threading.RLock()
        self._reconciliation_locked = False
        self._kill_switch_active = False

    @property
    def current_state(self) -> CircuitState:
        with self._lock:
            if self._kill_switch_active or self._state == CircuitState.HARD_HALT:
                return CircuitState.HARD_HALT
            if self._reconciliation_locked or self._state == CircuitState.REDUCE_ONLY:
                return CircuitState.REDUCE_ONLY
            return CircuitState.NORMAL

    def trigger_kill_switch(self, reason: str = "EMERGENCY_KILL_SWITCH_ACTIVATED") -> None:
        """Triggers permanent emergency HARD_HALT dominating all authorities."""
        with self._lock:
            self._kill_switch_active = True
            self._state = CircuitState.HARD_HALT

    def trigger_reconciliation_lock(self, reason: str = "STATE_UNCERTAINTY_OR_TIMEOUT") -> None:
        """Triggers REDUCE_ONLY lock due to state uncertainty or network timeout (Invariant 4J-P11)."""
        with self._lock:
            self._reconciliation_locked = True

    def trigger_circuit_breaker(self, state: CircuitState) -> None:
        """Transitions circuit breaker to REDUCE_ONLY or HARD_HALT."""
        with self._lock:
            if self._kill_switch_active:
                return  # Kill switch dominates
            if state == CircuitState.HARD_HALT:
                self._state = CircuitState.HARD_HALT
            elif state == CircuitState.REDUCE_ONLY and self._state != CircuitState.HARD_HALT:
                self._state = CircuitState.REDUCE_ONLY

    def can_execute_order(self, is_risk_reducing: bool = False) -> Tuple[bool, str]:
        """
        Evaluates whether an order can proceed based on current circuit state.
        HARD_HALT -> Denies ALL orders.
        REDUCE_ONLY -> Permits risk-reducing orders; denies risk-increasing orders.
        """
        with self._lock:
            st = self.current_state
            if st == CircuitState.HARD_HALT:
                return False, "DISPATCH_DENIED: HARD_HALT active (all execution blocked)"
            if st == CircuitState.REDUCE_ONLY:
                if is_risk_reducing:
                    return True, "AUTHORIZED: Risk-reducing order permitted under REDUCE_ONLY"
                return False, "DISPATCH_DENIED: Risk-increasing order blocked under REDUCE_ONLY"
            return True, "AUTHORIZED: Circuit breaker normal"

    def reset_for_testing(self) -> None:
        """Resets state for testing purposes."""
        with self._lock:
            self._state = CircuitState.NORMAL
            self._reconciliation_locked = False
            self._kill_switch_active = False
