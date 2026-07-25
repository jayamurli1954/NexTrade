# pilot/session_manager.py
"""
Live Session Manager & Lifecycle Controller for NexTrade (Sub-Phase 4K).
Manages pilot session state transitions, stage escalation governance (Invariant 4K-P2),
session expiry, and explicit closure procedures (Invariant 4K-P10).
"""
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Tuple

from contracts.pilot_contracts import PilotSessionConfig, PilotStage, PreflightCertificate


class SessionState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    ABORTED = "ABORTED"


class PilotSessionManager:
    """
    Thread-safe session manager enforcing finite validity windows and stage escalation bounds.
    """

    def __init__(self):
        self._state = SessionState.UNINITIALIZED
        self._config: Optional[PilotSessionConfig] = None
        self._certificate: Optional[PreflightCertificate] = None
        self._lock = threading.RLock()

    @property
    def current_state(self) -> SessionState:
        with self._lock:
            if self._config and datetime.now(timezone.utc) > self._config.session_expires_at:
                if self._state == SessionState.ACTIVE:
                    self._state = SessionState.CLOSED
            return self._state

    def start_session(
        self,
        config: PilotSessionConfig,
        certificate: PreflightCertificate
    ) -> Tuple[bool, str]:
        """
        Initializes an ACTIVE pilot session given a valid PreflightCertificate.
        """
        with self._lock:
            if certificate.session_id != config.session_id:
                return False, "SESSION_START_DENIED: PreflightCertificate session_id mismatch"

            now = datetime.now(timezone.utc)
            if now > config.session_expires_at:
                return False, "SESSION_START_DENIED: PilotSessionConfig expiration timestamp has passed"

            self._config = config
            self._certificate = certificate
            self._state = SessionState.ACTIVE
            return True, f"SESSION_ACTIVE: Pilot session {config.session_id} started at stage {config.pilot_stage.value}"

    def escalate_stage(
        self,
        target_stage: PilotStage,
        operator_reauthorization_id: str
    ) -> Tuple[bool, str]:
        """
        Escalates pilot stage (Invariant 4K-P2). Requires explicit operator re-authorization.
        """
        with self._lock:
            if self.current_state != SessionState.ACTIVE:
                return False, f"ESCALATION_DENIED: Session is not ACTIVE (current: {self._state.value})"

            if not operator_reauthorization_id:
                return False, "ESCALATION_DENIED: Explicit human re-authorization ID required"

            # Update config with new stage
            self._config = PilotSessionConfig(
                session_id=self._config.session_id,
                pilot_stage=target_stage,
                max_daily_orders=self._config.max_daily_orders,
                max_cumulative_exposure=self._config.max_cumulative_exposure,
                max_daily_loss=self._config.max_daily_loss,
                max_concurrent_positions=2 if target_stage == PilotStage.STAGE_2_SUPERVISED else 1,
                approved_symbols=self._config.approved_symbols,
                operator_id=self._config.operator_id,
                session_expires_at=self._config.session_expires_at,
                config_hash=self._config.config_hash
            )
            return True, f"ESCALATION_SUCCESS: Session escalated to {target_stage.value}"

    def close_session(self, reason: str = "NORMAL_SESSION_CLOSURE") -> Tuple[bool, str]:
        """Closes active session cleanly."""
        with self._lock:
            self._state = SessionState.CLOSED
            return True, f"SESSION_CLOSED: {reason}"

    def abort_session(self, reason: str = "EMERGENCY_SESSION_ABORT") -> Tuple[bool, str]:
        """Aborts session immediately into ABORTED state."""
        with self._lock:
            self._state = SessionState.ABORTED
            return True, f"SESSION_ABORTED: {reason}"
