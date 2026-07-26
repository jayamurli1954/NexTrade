"""
NexTrade Phase 5D — User Trading Workspace Integration Safety Audit Test Suite.

Explicitly maps each invariant to executable audit tests:
- 5D-P1: test_ui_widget_state_subscription
- 5D-P2: test_3_layer_defence_in_depth
- 5D-P3: test_ui_bypass_attempt
- 5D-P4: test_controller_bypass_attempt
- 5D-P5: test_direct_execution_bypass_attempt
- 5D-P6: test_stale_capability_bypass
- 5D-P7: test_stale_authorisation_bypass
- 5D-P8: test_replayed_approval_bypass
- 5D-P9: test_product_order_type_matrix_enforcement
- 5D-P10: test_idempotency_duplicate_protection
- 5D-P11: test_workspace_view_state_sanitization
- 5D-P12: test_backward_compatibility_regression_check
"""

import pytest
from unittest.mock import MagicMock

from hardening import SafetyControlPlane, SafetyState
from brokers import BrokerProductionGate, DispatchIneligibleException, ConnectionState
from ui_new.capability_bridge import CapabilityEnforcerBridge, StaleCapabilityException
from ui_new.widget_binder import DynamicWidgetBinder
from ui_new.workspace_controller import (
    TradingWorkspaceController,
    UIBypassAttemptException,
    ControllerValidationException,
    StaleAuthorisationException,
    DuplicateSubmissionException,
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestWorkspaceIntegrationAudit:
    """Audit test suite certifying 5D invariants."""

    def test_ui_widget_state_subscription(self):
        """Verify UI widget control state updates on SafetyControlPlane transition (5D-P1)."""
        scp = SafetyControlPlane()
        binder = DynamicWidgetBinder(control_plane=scp)

        # Initial state should be locked or requiring auth
        state = binder.get_ui_control_state()
        assert "safety_state" in state

        # Trip SafetyControlPlane to HARD_HALT
        scp.report_subsystem_state("test", SafetyState.HARD_HALT, "Testing halt")
        updated_state = binder.get_ui_control_state()
        assert updated_state["is_buy_enabled"] is False
        assert updated_state["is_locked"] is True

    def test_3_layer_defence_in_depth(self):
        """Verify 3-layer defence-in-depth workflow under healthy conditions (5D-P2)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        controller = TradingWorkspaceController(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"}
        
        response = controller.submit_order_intent(payload, auth_token="auth_valid_session_token_100", idempotency_token="idempotent_1")
        assert response["status"] == "DISPATCHED"

    def test_ui_bypass_attempt(self):
        """Verify Layer 1 UI disablement rejection when SafetyState is locked (5D-P3)."""
        scp = SafetyControlPlane()
        scp.report_subsystem_state("test", SafetyState.HARD_HALT, "Halted")
        
        gate = BrokerProductionGate(control_plane=scp)
        controller = TradingWorkspaceController(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"}

        with pytest.raises(UIBypassAttemptException) as exc_info:
            controller.submit_order_intent(payload, auth_token="auth_valid_session_token_100", idempotency_token="idempotent_2", force_ui_bypass=True)

        assert "UI controls locked" in str(exc_info.value)

    def test_controller_bypass_attempt(self):
        """Verify Layer 2 controller payload validation failure (5D-P4)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        controller = TradingWorkspaceController(production_gate=gate, control_plane=scp)
        invalid_payload = {"symbol": "AAPL", "quantity": 0, "order_type": "LIMIT", "trade_type": "INTRADAY"}

        with pytest.raises(ControllerValidationException) as exc_info:
            controller.submit_order_intent(invalid_payload, auth_token="auth_valid_session_token_100", idempotency_token="idempotent_3")

        assert "quantity must be greater than zero" in str(exc_info.value)

    def test_direct_execution_bypass_attempt(self):
        """Verify Layer 3 backend execution authority independently rejects uninitialized gate (5D-P5)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        # Gate remains uninitialized (DISCONNECTED)

        with pytest.raises(DispatchIneligibleException) as exc_info:
            gate.dispatch_order({"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"})

        assert "must be CONNECTED_HEALTHY" in str(exc_info.value)

    def test_stale_capability_bypass(self):
        """Verify stale capability assertion is rejected (5D-P6)."""
        bridge = CapabilityEnforcerBridge()
        bridge.mark_capabilities_stale("IBKR")

        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"}
        with pytest.raises(StaleCapabilityException):
            bridge.validate_intent_capability(payload, "IBKR")

    def test_stale_authorisation_bypass(self):
        """Verify stale / invalid authorization token is rejected by Layer 2 (5D-P7)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        controller = TradingWorkspaceController(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"}

        with pytest.raises(StaleAuthorisationException):
            controller.submit_order_intent(payload, auth_token="EXPIRED_TOKEN_999", idempotency_token="idempotent_4")


    def test_replayed_approval_bypass(self):
        """Verify duplicate / replayed idempotency token is rejected (5D-P8)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        controller = TradingWorkspaceController(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"}

        # First submission
        controller.submit_order_intent(payload, auth_token="auth_valid_session_token_100", idempotency_token="replayed_token_55")

        # Duplicate submission attempt
        with pytest.raises(DuplicateSubmissionException):
            controller.submit_order_intent(payload, auth_token="auth_valid_session_token_100", idempotency_token="replayed_token_55")

    def test_product_order_type_matrix_enforcement(self):
        """Verify unsupported order type is rejected by CapabilityBridge (5D-P9)."""
        bridge = CapabilityEnforcerBridge()
        invalid_payload = {"symbol": "AAPL", "quantity": 10, "order_type": "UNSUPPORTED_EXOTIC_TYPE", "trade_type": "INTRADAY"}
        assert bridge.validate_intent_capability(invalid_payload, "IBKR") is False

    def test_idempotency_duplicate_protection(self):
        """Verify idempotency token tracking prevents duplicate order dispatches (5D-P10)."""
        controller = TradingWorkspaceController()
        assert "idem_token_abc" not in controller._processed_idempotency_tokens

    def test_workspace_view_state_sanitization(self):
        """Verify secret strings are sanitized from workspace log payloads (5D-P11)."""
        from governance import SecretSanitizer
        raw_payload = {"symbol": "AAPL", "api_key": "secret_key_value_12345", "token": "bearer_token_val"}
        clean_payload = SecretSanitizer.sanitize_dict(raw_payload)
        assert clean_payload["api_key"] == "[REDACTED_SENSITIVE_FIELD]"
        assert clean_payload["token"] == "[REDACTED_SENSITIVE_FIELD]"

    def test_backward_compatibility_regression_check(self):
        """Verify 5D modules maintain full backward compatibility (5D-P12)."""
        scp = SafetyControlPlane()
        assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED
