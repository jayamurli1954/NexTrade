# resilience/incident_manager.py
"""
Central Incident Manager & Escalation Controller for NexTrade (Sub-Phase 4L).
Monitors operational health, logs immutable IncidentRecords, triggers automatic fail-closed actions
(HARD_HALT, REDUCE_ONLY), and tracks operator acknowledgements (Invariants 4L-P1, 4L-P2, 4L-P8).
"""
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

from contracts.resilience_contracts import IncidentRecord, IncidentSeverity


class IncidentManager:
    """
    Thread-safe incident manager enforcing fail-closed escalation and explicit human operator acknowledgement.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._incidents: List[IncidentRecord] = []
        self._current_mode = "NORMAL"  # NORMAL, REDUCE_ONLY, HARD_HALT
        self._reconciliation_locked = False

    @property
    def current_mode(self) -> str:
        with self._lock:
            return self._current_mode

    @property
    def is_reconciliation_locked(self) -> bool:
        with self._lock:
            return self._reconciliation_locked

    def report_incident(
        self,
        subsystem: str,
        severity: IncidentSeverity,
        description: str
    ) -> IncidentRecord:
        """
        Logs a system incident and triggers automatic fail-closed responses (Invariant 4L-P1).
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            inc_id = f"INC-{uuid.uuid4().hex[:12].upper()}"

            # Determine fail-closed action based on severity
            triggered_action = "NORMAL"
            if severity in (IncidentSeverity.CRITICAL, IncidentSeverity.FATAL):
                triggered_action = "HARD_HALT"
                self._current_mode = "HARD_HALT"
                self._reconciliation_locked = True
            elif severity == IncidentSeverity.HIGH:
                triggered_action = "REDUCE_ONLY"
                if self._current_mode != "HARD_HALT":
                    self._current_mode = "REDUCE_ONLY"

            record = IncidentRecord(
                incident_id=inc_id,
                subsystem=subsystem,
                severity=severity,
                description=description,
                triggered_action=triggered_action,
                operator_acknowledged=False,
                timestamp=now
            )
            self._incidents.append(record)
            return record

    def acknowledge_incident(
        self,
        incident_id: str,
        operator_id: str
    ) -> Tuple[bool, str]:
        """
        Records human operator acknowledgement for an incident (Invariant 4L-P8).
        """
        with self._lock:
            if not operator_id:
                return False, "ACK_DENIED: Operator ID is required for incident acknowledgement"

            for idx, inc in enumerate(self._incidents):
                if inc.incident_id == incident_id:
                    self._incidents[idx] = IncidentRecord(
                        incident_id=inc.incident_id,
                        subsystem=inc.subsystem,
                        severity=inc.severity,
                        description=inc.description,
                        triggered_action=inc.triggered_action,
                        operator_acknowledged=True,
                        timestamp=inc.timestamp
                    )
                    return True, f"ACK_SUCCESS: Incident {incident_id} acknowledged by operator {operator_id}"

            return False, f"ACK_DENIED: Incident {incident_id} not found"

    def get_unacknowledged_incidents(self) -> List[IncidentRecord]:
        """Returns list of unacknowledged incidents."""
        with self._lock:
            return [inc for inc in self._incidents if not inc.operator_acknowledged]

    def reset_incident_state(self, operator_recovery_id: str) -> Tuple[bool, str]:
        """
        Resets incident escalation state back to NORMAL only with explicit human operator recovery ID (Invariant 4L-P2).
        Note: Enforces Invariant 4L-P4 (Resets mode to SAFE/NORMAL, but DOES NOT grant execution authority).
        """
        with self._lock:
            if not operator_recovery_id:
                return False, "RESET_DENIED: Operator recovery ID required for incident state reset"

            unacked = self.get_unacknowledged_incidents()
            if unacked:
                return False, f"RESET_DENIED: Cannot reset while {len(unacked)} unacknowledged incidents remain"

            self._current_mode = "NORMAL"
            self._reconciliation_locked = False
            return True, f"RESET_SUCCESS: Incident state reset to NORMAL by operator {operator_recovery_id} (Authority reset to SAFE)"
