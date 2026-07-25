# resilience/disconnect_handler.py
"""
Broker Disconnect & Reconnect Recovery Handler for NexTrade (Sub-Phase 4L).
Handles broker stream disconnects, enforces immediate fail-closed state, triggers reconciliation locks,
and blocks new order submissions (Invariant 4L-P3).
"""
import threading
from typing import Tuple, Optional


class DisconnectHandler:
    """
    Thread-safe broker disconnect handler enforcing zero dispatch during connectivity outages.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._connection_status = "CONNECTED"  # CONNECTED, DISCONNECTED, RECONNECTING
        self._reconciliation_required = False

    @property
    def connection_status(self) -> str:
        with self._lock:
            return self._connection_status

    @property
    def reconciliation_required(self) -> bool:
        with self._lock:
            return self._reconciliation_required

    def handle_disconnect(self, reason: str = "STREAM_DISCONNECTED") -> Tuple[bool, str]:
        """
        Triggered when broker socket/stream disconnects (Invariant 4L-P3).
        Forces DISCONNECTED status and locks reconciliation.
        """
        with self._lock:
            self._connection_status = "DISCONNECTED"
            self._reconciliation_required = True
            return True, f"DISCONNECT_HANDLED: Connection status set to DISCONNECTED due to '{reason}'. Reconciliation locked."

    def handle_reconnect_attempt(self) -> Tuple[bool, str]:
        """Triggers RECONNECTING status."""
        with self._lock:
            self._connection_status = "RECONNECTING"
            return True, "RECONNECTING: Attempting broker stream re-establishment"

    def complete_reconnect_with_reconciliation(
        self,
        reconciliation_passed: bool,
        operator_id: str
    ) -> Tuple[bool, str]:
        """
        Completes reconnect only if position reconciliation passes (Invariants 4L-P3, 4L-P7).
        """
        with self._lock:
            if not operator_id:
                return False, "RECONNECT_DENIED: Operator ID required for reconnect completion"

            if not reconciliation_passed:
                self._connection_status = "DISCONNECTED"
                self._reconciliation_required = True
                return False, "RECONNECT_DENIED: Position reconciliation failed during reconnect verification"

            self._connection_status = "CONNECTED"
            self._reconciliation_required = False
            return True, f"RECONNECT_SUCCESS: Connection restored and reconciled by operator {operator_id}"
