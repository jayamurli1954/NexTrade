"""
NexTrade Phase 5A — Safety Control Plane & Canonical SafetyState Management.

Authoritative Safety Control Plane observing and governing execution, capability, risk,
and UI components. Manages canonical SafetyState and precedence hierarchy.
"""

from enum import IntEnum, auto
import threading
import logging
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger("SafetyControlPlane")


class SafetyState(IntEnum):
    """
    Canonical SafetyState Enum with strict precedence hierarchy.
    Higher integer value indicates higher severity / precedence.
    """
    SAFE = 0
    READY = 1
    HOLD = 2
    AUTHORIZATION_REQUIRED = 3
    REVALIDATION_REQUIRED = 4
    BROKER_DISCONNECTED = 5
    RECONCILIATION_LOCK = 6
    HARD_HALT = 7
    EMERGENCY_KILL = 8

    def is_execution_permitted(self) -> bool:
        """Returns True ONLY if state permits active execution dispatch."""
        return self in (SafetyState.SAFE, SafetyState.READY)

    def is_halted(self) -> bool:
        """Returns True if the system is in a hard halted or killed state."""
        return self in (SafetyState.EMERGENCY_KILL, SafetyState.HARD_HALT, SafetyState.RECONCILIATION_LOCK)


class SafetyControlPlane:
    """
    Centralized, authoritative Safety Control Plane singleton.
    Governs state transitions, precedence ladder resolution, listener notifications,
    and kill switch / circuit breaker assertions.
    """

    _instance: Optional["SafetyControlPlane"] = None
    _lock = threading.RLock()

    def __new__(cls) -> "SafetyControlPlane":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SafetyControlPlane, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        with self._lock:
            if getattr(self, "_initialized", False):
                return
            self._current_state: SafetyState = SafetyState.AUTHORIZATION_REQUIRED
            self._listeners: List[Callable[[SafetyState, SafetyState, str], None]] = []
            self._subsystem_states: Dict[str, SafetyState] = {}
            self._active_kill_switches: Set[str] = set()
            self._active_circuit_breakers: Set[str] = set()
            self._history: List[Dict[str, str]] = []
            self._initialized = True
            logger.info("SafetyControlPlane initialized in state: %s", self._current_state.name)

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance for test isolation."""
        with cls._lock:
            if cls._instance:
                cls._instance._initialized = False
                cls._instance = None

    def get_state(self) -> SafetyState:
        """Get current canonical SafetyState."""
        with self._lock:
            return self._current_state

    def register_listener(self, callback: Callable[[SafetyState, SafetyState, str], None]) -> None:
        """
        Register a subscriber callback(old_state, new_state, reason) for state changes.
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[SafetyState, SafetyState, str], None]) -> None:
        """Unregister a state change listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def report_subsystem_state(self, subsystem_id: str, state: SafetyState, reason: str = "") -> SafetyState:
        """
        Report state from a specific subsystem (e.g. 'broker', 'reconciler', 'hardener').
        Evaluates canonical state based on precedence hierarchy.
        """
        with self._lock:
            self._subsystem_states[subsystem_id] = state
            logger.debug("Subsystem '%s' reported state: %s (reason: %s)", subsystem_id, state.name, reason)
            return self._reevaluate_canonical_state(reason=f"Subsystem '{subsystem_id}' reported {state.name}: {reason}")

    def trigger_emergency_kill(self, reason: str, authority: str = "SYSTEM") -> None:
        """
        Trigger immediate emergency kill switch.
        """
        with self._lock:
            self._active_kill_switches.add(authority)
            self.report_subsystem_state("EMERGENCY_KILL_SWITCH", SafetyState.EMERGENCY_KILL, f"Triggered by {authority}: {reason}")

    def trip_circuit_breaker(self, breaker_name: str, reason: str) -> None:
        """
        Trip a circuit breaker.
        """
        with self._lock:
            self._active_circuit_breakers.add(breaker_name)
            self.report_subsystem_state(f"breaker_{breaker_name}", SafetyState.HARD_HALT, f"Breaker '{breaker_name}' tripped: {reason}")

    def reset_circuit_breaker(self, breaker_name: str, authority: str) -> None:
        """
        Reset a circuit breaker. Subsystem state removed.
        """
        with self._lock:
            if breaker_name in self._active_circuit_breakers:
                self._active_circuit_breakers.remove(breaker_name)
            self._subsystem_states.pop(f"breaker_{breaker_name}", None)
            logger.info("Circuit breaker '%s' reset by authority '%s'", breaker_name, authority)
            self._reevaluate_canonical_state(reason=f"Breaker '{breaker_name}' reset by {authority}")

    def set_override_state(self, new_state: SafetyState, reason: str) -> SafetyState:
        """
        Set explicit override state. Still respects active EMERGENCY_KILL or HARD_HALT
        if the override attempts to set a less restrictive state than active kill switches.
        """
        with self._lock:
            return self._reevaluate_canonical_state(explicit_state=new_state, reason=reason)

    def _reevaluate_canonical_state(self, explicit_state: Optional[SafetyState] = None, reason: str = "") -> SafetyState:
        """
        Evaluates effective canonical state using precedence hierarchy:
        Max severity across subsystem states and explicit requests.
        """
        with self._lock:
            candidates: List[SafetyState] = list(self._subsystem_states.values())
            if explicit_state is not None:
                candidates.append(explicit_state)

            if not candidates:
                effective_state = SafetyState.AUTHORIZATION_REQUIRED
            else:
                effective_state = max(candidates, key=lambda s: s.value)

            old_state = self._current_state
            if old_state != effective_state:
                self._current_state = effective_state
                log_entry = {
                    "from": old_state.name,
                    "to": effective_state.name,
                    "reason": reason
                }
                self._history.append(log_entry)
                logger.warning("SafetyControlPlane state transition: %s -> %s (Reason: %s)",
                               old_state.name, effective_state.name, reason)

                # Notify listeners outside of potential lock re-entry deadlocks
                listeners = list(self._listeners)
                for listener in listeners:
                    try:
                        listener(old_state, effective_state, reason)
                    except Exception as e:
                        logger.error("Error notifying SafetyControlPlane listener: %s", str(e), exc_info=True)

            return self._current_state

    def get_subsystem_states(self) -> Dict[str, SafetyState]:
        """Returns snapshot of subsystem states."""
        with self._lock:
            return dict(self._subsystem_states)

    def get_history(self) -> List[Dict[str, str]]:
        """Returns copy of state change history."""
        with self._lock:
            return list(self._history)
