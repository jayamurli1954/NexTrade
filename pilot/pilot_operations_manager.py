"""
NexTrade Phase 5G — Pilot Operations Manager.

Governs pilot trading sessions with exposure limits (max position size, max daily loss, order rate)
and enforces fail-closed safety override prevention.
"""

import time
import logging
from typing import Dict, Any, Optional

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from governance.execution_time_authorizer import ExecutionTimeAuthorizer, ExecutionAuthorizationException
from governance.secret_sanitizer import SecretSanitizer

logger = logging.getLogger("PilotOperationsManager")


class PilotExposureLimitExceededException(Exception):
    """Raised when a pilot order violates pilot exposure bounds (position size, drawdown, order rate)."""
    pass


class PilotSafetyOverrideException(Exception):
    """Raised when a pilot execution attempt tries to bypass or override SafetyControlPlane controls."""
    pass


class PilotOperationsManager:
    """
    Manager governing pilot trading session exposure and safety compliance.
    """

    def __init__(
        self,
        execution_authorizer: Optional[ExecutionTimeAuthorizer] = None,
        control_plane: Optional[SafetyControlPlane] = None,
        max_position_size: float = 1000.0,
        max_daily_loss: float = 5000.0,
        max_orders_per_min: int = 60
    ) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.authorizer = execution_authorizer or ExecutionTimeAuthorizer(control_plane=self.control_plane)
        
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.max_orders_per_min = max_orders_per_min
        
        self._current_daily_loss: float = 0.0
        self._order_timestamps: list = []

    def record_realized_loss(self, loss_amount: float) -> None:
        """Records realized loss and checks daily drawdown limit."""
        self._current_daily_loss += max(0.0, loss_amount)
        if self._current_daily_loss >= self.max_daily_loss:
            err = f"Pilot max daily loss limit exceeded ({self._current_daily_loss:.2f} >= {self.max_daily_loss:.2f}). Tripping SafetyState to HOLD."
            logger.critical(err)
            self.control_plane.report_subsystem_state("pilot_operations", SafetyState.HOLD, err)

    def validate_pilot_order_exposure(self, order_payload: Dict[str, Any]) -> None:
        """Validates order size and velocity rate limits."""
        quantity = float(order_payload.get("quantity", 0))
        price = float(order_payload.get("price", 1.0))
        position_value = quantity * price

        if position_value > self.max_position_size:
            err = f"Pilot order value ({position_value:.2f}) exceeds max position limit ({self.max_position_size:.2f})"
            logger.warning(err)
            raise PilotExposureLimitExceededException(err)

        now = time.time()
        self._order_timestamps = [t for t in self._order_timestamps if now - t <= 60.0]
        if len(self._order_timestamps) >= self.max_orders_per_min:
            err = f"Pilot order velocity limit exceeded ({len(self._order_timestamps)} orders/min >= {self.max_orders_per_min})"
            logger.warning(err)
            raise PilotExposureLimitExceededException(err)

        self._order_timestamps.append(now)

    def submit_pilot_order_intent(
        self,
        order_payload: Dict[str, Any],
        session_token: str = "auth_valid_session_token_100",
        idempotency_token: str = "pilot_idem_1",
        force_override: bool = False
    ) -> Dict[str, Any]:
        """
        Submits pilot order intent enforcing pilot exposure limits and full 5A-5F safety clearance.
        Rejects force_override attempts.
        """
        sanitized = SecretSanitizer.sanitize_dict(order_payload)
        logger.info("Evaluating pilot order intent: %s", sanitized)

        if force_override:
            err = "Pilot mode cannot override or bypass SafetyControlPlane controls! Request rejected."
            logger.critical(err)
            raise PilotSafetyOverrideException(err)

        # 1. Validate pilot exposure limits
        self.validate_pilot_order_exposure(order_payload)

        # 2. Authorize execution via 4-layer ExecutionTimeAuthorizer
        try:
            return self.authorizer.authorize_execution_intent(
                order_payload=order_payload,
                session_token=session_token,
                idempotency_token=idempotency_token
            )
        except ExecutionAuthorizationException as e:
            logger.warning("Pilot order rejected by 5E ExecutionTimeAuthorizer: %s", str(e))
            raise

    def generate_pilot_evidence_log(self) -> Dict[str, Any]:
        """Generates evidence summary for pilot session operational audit."""
        return SecretSanitizer.sanitize_dict({
            "pilot_status": "ACTIVE",
            "current_daily_loss": self._current_daily_loss,
            "max_daily_loss": self.max_daily_loss,
            "orders_last_min": len(self._order_timestamps),
            "safety_state": self.control_plane.get_state().name
        })
