"""
NexTrade Phase 5B — Broker Connection State Machine & Fault Classifier.

Separates ConnectionState (7-state lifecycle) from ConnectionFault reasons.
Enforces dispatch eligibility strictly when state == CONNECTED_HEALTHY.
"""

from enum import Enum, IntEnum
import threading
import logging
from typing import Optional, Tuple

from hardening.safety_control_plane import SafetyControlPlane, SafetyState

logger = logging.getLogger("BrokerConnectionStateMachine")


class ConnectionState(Enum):
    """
    Explicit 7-state broker connection lifecycle.
    """
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    TLS_VALIDATING = "TLS_VALIDATING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED_DEGRADED = "CONNECTED_DEGRADED"
    CONNECTED_HEALTHY = "CONNECTED_HEALTHY"
    DISCONNECTING = "DISCONNECTING"


class ConnectionFault(Enum):
    """
    Distinct connection fault reasons for auditability and incident logging.
    """
    NONE = "NONE"
    TLS_FAILURE = "TLS_FAILURE"
    AUTH_FAILURE = "AUTH_FAILURE"
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    LATENCY_BREACH = "LATENCY_BREACH"
    ORDER_ACK_UNKNOWN = "ORDER_ACK_UNKNOWN"
    CANCEL_ACK_UNKNOWN = "CANCEL_ACK_UNKNOWN"


class BrokerConnectionStateMachine:
    """
    State machine managing broker connection lifecycle and fault transitions.
    Coordinates fault reporting with SafetyControlPlane.
    """

    def __init__(self, broker_id: str, control_plane: Optional[SafetyControlPlane] = None) -> None:
        self.broker_id = broker_id
        self.control_plane = control_plane or SafetyControlPlane()
        self._state = ConnectionState.DISCONNECTED
        self._fault = ConnectionFault.NONE
        self._lock = threading.RLock()

    @property
    def current_state(self) -> ConnectionState:
        with self._lock:
            return self._state

    @property
    def current_fault(self) -> ConnectionFault:
        with self._lock:
            return self._fault

    def is_dispatch_eligible(self) -> bool:
        """
        Returns True ONLY if connection state is CONNECTED_HEALTHY and fault is NONE.
        """
        with self._lock:
            return self._state == ConnectionState.CONNECTED_HEALTHY and self._fault == ConnectionFault.NONE

    def transition_to(self, target_state: ConnectionState, fault: ConnectionFault = ConnectionFault.NONE, reason: str = "") -> Tuple[ConnectionState, ConnectionFault]:
        """
        Executes connection state transition and reports subsystem state to SafetyControlPlane.
        """
        with self._lock:
            old_state = self._state
            old_fault = self._fault
            self._state = target_state
            self._fault = fault

            logger.info("Broker '%s' connection transition: %s (%s) -> %s (%s) [Reason: %s]",
                        self.broker_id, old_state.value, old_fault.value, target_state.value, fault.value, reason)

            # Map connection faults to SafetyControlPlane requests
            if fault in (ConnectionFault.HEARTBEAT_TIMEOUT, ConnectionFault.TLS_FAILURE, ConnectionFault.AUTH_FAILURE):
                self.control_plane.report_subsystem_state(
                    f"broker_conn_{self.broker_id}",
                    SafetyState.BROKER_DISCONNECTED,
                    f"Broker {self.broker_id} connection fault: {fault.value} ({reason})"
                )
            elif fault == ConnectionFault.MARKET_DATA_STALE:
                self.control_plane.report_subsystem_state(
                    f"broker_conn_{self.broker_id}",
                    SafetyState.HOLD,
                    f"Market data stale for {self.broker_id}: {reason}"
                )
            elif fault == ConnectionFault.LATENCY_BREACH:
                self.control_plane.report_subsystem_state(
                    f"broker_conn_{self.broker_id}",
                    SafetyState.HARD_HALT,
                    f"Latency hard limit breach for {self.broker_id}: {reason}"
                )
            elif fault in (ConnectionFault.ORDER_ACK_UNKNOWN, ConnectionFault.CANCEL_ACK_UNKNOWN):
                self.control_plane.report_subsystem_state(
                    f"broker_conn_{self.broker_id}",
                    SafetyState.RECONCILIATION_LOCK,
                    f"Execution ACK uncertainty ({fault.value}) for {self.broker_id}: {reason}"
                )
            elif target_state == ConnectionState.CONNECTED_HEALTHY and fault == ConnectionFault.NONE:
                self.control_plane.report_subsystem_state(
                    f"broker_conn_{self.broker_id}",
                    SafetyState.READY,
                    f"Broker {self.broker_id} connection healthy"
                )

            return self._state, self._fault

    def record_fault(self, fault: ConnectionFault, reason: str) -> None:
        """Record a fault and transition state accordingly."""
        with self._lock:
            target_state = ConnectionState.CONNECTED_DEGRADED
            if fault in (ConnectionFault.TLS_FAILURE, ConnectionFault.AUTH_FAILURE, ConnectionFault.HEARTBEAT_TIMEOUT):
                target_state = ConnectionState.DISCONNECTED
            self.transition_to(target_state, fault, reason)
