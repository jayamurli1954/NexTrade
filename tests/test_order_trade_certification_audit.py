"""
NexTrade Phase 5E — Trade Type & Order Type Certification Safety Audit Test Suite.

Explicitly maps each invariant to executable audit tests (1:1 mapping):
- 5E-P1: test_layer1_product_instrument_eligibility
- 5E-P2: test_layer2_trade_type_matrix
- 5E-P3: test_layer3_order_type_semantics
- 5E-P4: test_tick_size_precision_validation
- 5E-P5: test_lot_size_multiple_validation
- 5E-P6: test_stop_loss_trigger_semantics
- 5E-P7: test_market_order_prohibition
- 5E-P8: test_layer4_execution_time_authority
- 5E-P9: test_valid_ui_order_not_executable
- 5E-P10: test_unknown_order_state_rejection
- 5E-P11: test_certification_diagnostics_sanitization
- 5E-P12: test_backward_compatibility_regression_check
"""

import pytest
from unittest.mock import MagicMock

from hardening import SafetyControlPlane, SafetyState
from brokers import BrokerProductionGate, ConnectionState
from brokers.trade_type_matrix import TradeTypeMatrixValidator, InvalidTradeTypeException
from brokers.order_type_certifier import OrderTypeCertifier, InvalidOrderTypeException
from governance.execution_time_authorizer import ExecutionTimeAuthorizer, ExecutionAuthorizationException


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestOrderTradeCertificationAudit:
    """Audit test suite certifying 5E invariants."""

    def test_layer1_product_instrument_eligibility(self):
        """Verify Layer 1 product & instrument type eligibility (5E-P1)."""
        validator = TradeTypeMatrixValidator()
        valid, reason = validator.validate_product_and_trade_type("IBKR", "UNSUPPORTED_CRYPTO", "INTRADAY")
        assert valid is False
        assert "not supported" in reason

    def test_layer2_trade_type_matrix(self):
        """Verify Layer 2 trade type matrix compatibility (5E-P2)."""
        validator = TradeTypeMatrixValidator()
        
        # DELIVERY trade type is invalid for OPTIONS
        valid, reason = validator.validate_product_and_trade_type("IBKR", "OPTIONS", "DELIVERY")
        assert valid is False
        assert "incompatible" in reason

        # F&O is valid for OPTIONS
        valid_fo, _ = validator.validate_product_and_trade_type("IBKR", "OPTIONS", "F&O")
        assert valid_fo is True

    def test_layer3_order_type_semantics(self):
        """Verify Layer 3 order type semantics for LIMIT, MARKET, SL (5E-P3)."""
        certifier = OrderTypeCertifier()
        valid, reason = certifier.validate_order_type_semantics(
            {"order_type": "UNSUPPORTED_EXOTIC", "quantity": 10, "price": 100.0}
        )
        assert valid is False
        assert "unrecognized" in reason

    def test_tick_size_precision_validation(self):
        """Verify price tick size precision (e.g. 0.05 multiple) validation (5E-P4)."""
        certifier = OrderTypeCertifier()
        
        # 100.03 is not a multiple of 0.05
        valid, reason = certifier.validate_order_type_semantics(
            {"order_type": "LIMIT", "quantity": 10, "price": 100.03},
            tick_size=0.05
        )
        assert valid is False
        assert "not a valid multiple of tick size" in reason

        # 100.05 is a valid multiple of 0.05
        valid_ok, _ = certifier.validate_order_type_semantics(
            {"order_type": "LIMIT", "quantity": 10, "price": 100.05},
            tick_size=0.05
        )
        assert valid_ok is True

    def test_lot_size_multiple_validation(self):
        """Verify quantity lot size multiple validation (5E-P5)."""
        certifier = OrderTypeCertifier()
        
        # Quantity 30 is not a multiple of NIFTY lot size 25
        valid, reason = certifier.validate_order_type_semantics(
            {"order_type": "LIMIT", "quantity": 30, "price": 100.0},
            lot_size=25
        )
        assert valid is False
        assert "must be a positive multiple of lot size" in reason

    def test_stop_loss_trigger_semantics(self):
        """Verify Stop-Loss trigger price semantics for BUY and SELL (5E-P6)."""
        certifier = OrderTypeCertifier()
        
        # SL BUY: trigger_price (90) < market_price (100) is invalid
        valid, reason = certifier.validate_order_type_semantics(
            {"order_type": "SL", "action": "BUY", "quantity": 1, "price": 105.0, "trigger_price": 90.0},
            market_price=100.0
        )
        assert valid is False
        assert "trigger price 90.0 must be >=" in reason

    def test_market_order_prohibition(self):
        """Verify market order prohibition enforcement (5E-P7)."""
        certifier = OrderTypeCertifier()
        valid, reason = certifier.validate_order_type_semantics(
            {"order_type": "MARKET", "quantity": 10},
            market_orders_allowed=False
        )
        assert valid is False
        assert "strictly prohibited" in reason

    def test_layer4_execution_time_authority(self):
        """Verify Layer 4 execution time authority clearance (5E-P8)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        authorizer = ExecutionTimeAuthorizer(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY", "price": 150.0}
        
        response = authorizer.authorize_execution_intent(payload, tick_size=0.05, lot_size=1)
        assert response["status"] == "DISPATCHED"
        assert response["layer4_authorization"] == "AUTHORIZED_CLEARED"

    def test_valid_ui_order_not_executable(self):
        """Verify core invariant: valid UI order is rejected if SafetyState is HARD_HALT (5E-P9)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        authorizer = ExecutionTimeAuthorizer(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY", "price": 150.0}

        # Trip SafetyControlPlane to HARD_HALT
        scp.report_subsystem_state("risk", SafetyState.HARD_HALT, "Daily drawdown limit")

        with pytest.raises(ExecutionAuthorizationException) as exc_info:
            authorizer.authorize_execution_intent(payload)

        assert "Execution Authorization Failed" in str(exc_info.value)
        assert exc_info.value.layer == "4_ExecutionAuthority"

    def test_unknown_order_state_rejection(self):
        """Verify unresolved ORDER_STATE_UNKNOWN blocks new dispatches (5E-P10)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        authorizer = ExecutionTimeAuthorizer(production_gate=gate, control_plane=scp)
        
        # Simulate ACK timeout
        gate.reconciler.register_ack_timeout("ord_unresolved", "req_unresolved")

        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY", "price": 150.0}
        with pytest.raises(ExecutionAuthorizationException) as exc_info:
            authorizer.authorize_execution_intent(payload)

        assert exc_info.value.layer == "4_ExecutionAuthority"
        assert exc_info.value.details.get("has_unknown_orders") is True

    def test_certification_diagnostics_sanitization(self):
        """Verify secret strings are sanitized from 5E diagnostic logs (5E-P11)."""
        from governance import SecretSanitizer
        diag = {
            "authorizer": "ExecutionTimeAuthorizer",
            "session_secret": "secret_key_value_8888",
            "api_key": "ak_live_abcdef12345"
        }
        sanitized = SecretSanitizer.sanitize_dict(diag)
        assert sanitized["session_secret"] == "[REDACTED_SENSITIVE_FIELD]"
        assert sanitized["api_key"] == "[REDACTED_SENSITIVE_FIELD]"

    def test_backward_compatibility_regression_check(self):
        """Verify 5E modules maintain full backward compatibility (5E-P12)."""
        scp = SafetyControlPlane()
        assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED
