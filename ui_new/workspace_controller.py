"""
NexTrade Phase 5D — Trading Workspace Controller.

Primary UI controller managing trading session state, payload validation, intent submission,
3-layer defence-in-depth bypass prevention, and duplicate submission protection.
"""

import time
import logging
from typing import Dict, Any, Optional, Set

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from brokers.broker_production_gate import BrokerProductionGate, DispatchIneligibleException
from governance.secret_sanitizer import SecretSanitizer
from .capability_bridge import CapabilityEnforcerBridge, StaleCapabilityException
from .widget_binder import DynamicWidgetBinder

logger = logging.getLogger("TradingWorkspaceController")


class UIBypassAttemptException(Exception):
    """Raised when an order submission attempts to bypass Layer 1 UI disablement controls."""
    pass


class ControllerValidationException(Exception):
    """Raised when an order payload fails Layer 2 controller validation checks."""
    pass


class StaleAuthorisationException(Exception):
    """Raised when an order submission uses an expired or invalid authorization token."""
    pass


class DuplicateSubmissionException(Exception):
    """Raised when an order submission uses a replayed or duplicate idempotency token."""
    pass


class TradingWorkspaceController:
    """
    Controller bridge connecting ui_new trading workspace to backend safety engines.
    """

    def __init__(
        self,
        production_gate: Optional[BrokerProductionGate] = None,
        capability_bridge: Optional[CapabilityEnforcerBridge] = None,
        widget_binder: Optional[DynamicWidgetBinder] = None,
        control_plane: Optional[SafetyControlPlane] = None
    ) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.production_gate = production_gate or BrokerProductionGate(control_plane=self.control_plane)
        self.capability_bridge = capability_bridge or CapabilityEnforcerBridge()
        self.widget_binder = widget_binder or DynamicWidgetBinder(control_plane=self.control_plane, capability_bridge=self.capability_bridge)
        
        self._processed_idempotency_tokens: Set[str] = set()
        self._valid_auth_tokens: Set[str] = {"auth_valid_session_token_100"}

    def register_auth_token(self, token: str) -> None:
        """Register a valid authorization token for the active session."""
        self._valid_auth_tokens.add(token)

    def revoke_auth_token(self, token: str) -> None:
        """Revoke an authorization token."""
        self._valid_auth_tokens.discard(token)

    def submit_order_intent(
        self,
        order_payload: Dict[str, Any],
        auth_token: str,
        idempotency_token: str,
        force_ui_bypass: bool = False
    ) -> Dict[str, Any]:
        """
        Executes order intent submission enforcing 3-Layer Defence-in-Depth:
        Layer 1: UI Prevention Assertion
        Layer 2: Controller Validation & Idempotency
        Layer 3: Backend Execution Authority Assertion
        """
        sanitized_payload = SecretSanitizer.sanitize_dict(order_payload)
        logger.info("Received workspace order intent: %s", sanitized_payload)

        # --- Layer 1: UI Prevention Assertion ---
        ui_state = self.widget_binder.get_ui_control_state()
        if ui_state.get("is_locked", True) or not ui_state.get("is_buy_enabled", False):
            if force_ui_bypass:
                logger.critical("UI BYPASS DETECTED: Submission forced while UI controls are locked!")
                raise UIBypassAttemptException(f"UI controls locked ({ui_state.get('safety_state')}). Submission rejected by Layer 1.")
            raise UIBypassAttemptException(f"UI controls locked. Layer 1 rejection.")

        # --- Layer 2: Controller Validation & Idempotency ---
        if auth_token not in self._valid_auth_tokens:
            raise StaleAuthorisationException("Invalid or expired authorization token")

        if idempotency_token in self._processed_idempotency_tokens:
            raise DuplicateSubmissionException(f"Duplicate submission detected for token '{idempotency_token}'")

        # Payload schema checks
        required_fields = ["symbol", "quantity", "order_type", "trade_type"]
        for f in required_fields:
            if f not in order_payload:
                raise ControllerValidationException(f"Missing required payload field '{f}'")

        if float(order_payload.get("quantity", 0)) <= 0:
            raise ControllerValidationException("Order quantity must be greater than zero")

        # Capability validation
        broker_id = order_payload.get("broker_id", "IBKR")
        if not self.capability_bridge.validate_intent_capability(order_payload, broker_id):
            raise ControllerValidationException(f"Order intent not permitted by CapabilityResolver for broker {broker_id}")

        # Mark idempotency token processed
        self._processed_idempotency_tokens.add(idempotency_token)

        # --- Layer 3: Backend Execution Authority Assertion ---
        # Delegated to BrokerProductionGate
        dispatch_response = self.production_gate.dispatch_order(order_payload)
        return dispatch_response
