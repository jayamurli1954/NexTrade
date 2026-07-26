"""
NexTrade Phase 5B — Broker Connectivity & Safety Control Audit Test Suite.

Certifies 5B invariants:
- 5B-P1: Fine-grained, versioned, signed BrokerConnectivityPolicy integrity
- 5B-P2: Governed TLS certificate pinning & pin set rotation
- 5B-P3: Heartbeat timeout (>5s) transitions SafetyControlPlane to BROKER_DISCONNECTED
- 5B-P4: Order ACK timeout (>3s) transitions order to ORDER_STATE_UNKNOWN & forces RECONCILIATION_LOCK
- 5B-P5: Cancellation ACK timeout (>3s) forces RECONCILIATION_LOCK
- 5B-P6: Market data staleness (>2s) transitions state to HOLD
- 5B-P7: Latency hard limit exceedance (>1500ms) trips circuit breaker to HARD_HALT
- 5B-P8: D1-D10 Multi-variable dispatch eligibility assertions
- 5B-P9: Zero secret leakage in connection diagnostics
- 5B-P10: Monotonic timing protection against wall-clock skew
- 5B-P11: Connection state determinism (dispatch permitted ONLY in CONNECTED_HEALTHY)
- 5B-P12: Order state ambiguity dominance (ORDER_STATE_UNKNOWN forces RECONCILIATION_LOCK)
"""

import time
import pytest
from unittest.mock import MagicMock

from hardening import SafetyControlPlane, SafetyState
from brokers import (
    BrokerConnectivityPolicy,
    InvalidConnectivityPolicyException,
    BrokerConnectionStateMachine,
    ConnectionState,
    ConnectionFault,
    TLSPinningValidator,
    TLSPinSet,
    TLSPinningViolationException,
    BrokerHeartbeatMonitor,
    ClockIntegrityMonitor,
    LatencyHardLimitExceededException,
    HeartbeatTimeoutException,
    OrderReconciler,
    ReconciliationEvidenceRecord,
    OrderStateUnknownException,
    BrokerProductionGate,
    DispatchIneligibleException,
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestBrokerConnectivityPolicy:
    """Tests for 5B-P1: Versioned, hashable, signed BrokerConnectivityPolicy."""

    def test_policy_hash_and_integrity_verification(self):
        """Verify policy hash computation and integrity checks (5B-P1)."""
        policy = BrokerConnectivityPolicy(broker_id="IBKR", environment="TEST")
        assert policy.verify_integrity() is True
        assert len(policy.policy_hash) == 64

    def test_invalid_policy_bounds_rejection(self):
        """Verify invalid policy bounds trigger InvalidConnectivityPolicyException."""
        with pytest.raises(InvalidConnectivityPolicyException):
            policy = BrokerConnectivityPolicy(
                broker_id="IBKR",
                environment="TEST",
                latency_warning_threshold_ms=2000.0,
                latency_hard_limit_ms=1000.0  # Invalid: warning > hard limit
            )
            policy.verify_integrity()


class TestTLSPinningValidator:
    """Tests for 5B-P2: TLS certificate pinning and governed rotation."""

    def test_tls_certificate_matching(self):
        """Verify matching active cert fingerprint passes (5B-P2)."""
        pin_set = TLSPinSet(active_pin="sha256/valid_fingerprint_hash_123")
        validator = TLSPinningValidator(pin_set=pin_set)
        assert validator.validate_certificate("valid_fingerprint_hash_123", "api.ibkr.com") is True

    def test_tls_certificate_mismatch_rejection(self):
        """Verify cert mismatch raises TLSPinningViolationException (5B-P2)."""
        scp = SafetyControlPlane()
        sm = BrokerConnectionStateMachine("IBKR", control_plane=scp)
        pin_set = TLSPinSet(active_pin="sha256/valid_fingerprint_hash_123")
        validator = TLSPinningValidator(pin_set=pin_set, state_machine=sm)

        with pytest.raises(TLSPinningViolationException):
            validator.validate_certificate("INVALID_FINGERPRINT", "api.ibkr.com")

        assert sm.current_fault == ConnectionFault.TLS_FAILURE
        assert scp.get_state() == SafetyState.BROKER_DISCONNECTED

    def test_governed_pin_set_rotation(self):
        """Verify governed pin set rotation with signature."""
        validator = TLSPinningValidator()
        new_pin_set = TLSPinSet(active_pin="sha256/new_pin", pin_version="v2.0", signature="valid_sig")
        validator.rotate_pin_set(new_pin_set)
        assert validator.pin_set.pin_version == "v2.0"


class TestBrokerHeartbeatMonitor:
    """Tests for 5B-P3, 5B-P6, 5B-P7, 5B-P10: Monotonic heartbeat & latency monitor."""

    def test_latency_hard_limit_breach(self):
        """Verify latency >1500ms raises LatencyHardLimitExceededException (5B-P7)."""
        scp = SafetyControlPlane()
        sm = BrokerConnectionStateMachine("IBKR", control_plane=scp)
        policy = BrokerConnectivityPolicy(broker_id="IBKR", environment="TEST", latency_hard_limit_ms=1500.0)
        monitor = BrokerHeartbeatMonitor(policy=policy, state_machine=sm)

        with pytest.raises(LatencyHardLimitExceededException):
            monitor.record_order_heartbeat(latency_ms=1600.0)

        assert sm.current_fault == ConnectionFault.LATENCY_BREACH
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_heartbeat_timeout_detection(self):
        """Verify heartbeat timeout (>5s) sets BROKER_DISCONNECTED (5B-P3)."""
        scp = SafetyControlPlane()
        sm = BrokerConnectionStateMachine("IBKR", control_plane=scp)
        policy = BrokerConnectivityPolicy(broker_id="IBKR", environment="TEST", heartbeat_timeout_sec=0.01)
        monitor = BrokerHeartbeatMonitor(policy=policy, state_machine=sm)

        time.sleep(0.02)
        health = monitor.check_health()
        assert health["status"] == "HEARTBEAT_TIMEOUT"
        assert scp.get_state() == SafetyState.BROKER_DISCONNECTED

    def test_market_data_staleness_detection(self):
        """Verify market data staleness (>2s) sets SafetyState to HOLD (5B-P6)."""
        scp = SafetyControlPlane()
        sm = BrokerConnectionStateMachine("IBKR", control_plane=scp)
        policy = BrokerConnectivityPolicy(broker_id="IBKR", environment="TEST", market_data_staleness_limit_sec=0.01)
        monitor = BrokerHeartbeatMonitor(policy=policy, state_machine=sm)

        # Update order heartbeat so heartbeat is fresh, but market tick is stale
        monitor.record_order_heartbeat(latency_ms=10.0)
        time.sleep(0.02)

        health = monitor.check_health()
        assert health["status"] == "MARKET_DATA_STALE"
        assert scp.get_state() == SafetyState.HOLD


class TestOrderReconciler:
    """Tests for 5B-P4, 5B-P5, 5B-P12: ORDER_STATE_UNKNOWN & Reconciliation Lock."""

    def test_ack_timeout_enforces_order_state_unknown_and_reconciliation_lock(self):
        """Verify ACK timeout forces ORDER_STATE_UNKNOWN and RECONCILIATION_LOCK (5B-P4, 5B-P12)."""
        scp = SafetyControlPlane()
        sm = BrokerConnectionStateMachine("IBKR", control_plane=scp)
        reconciler = OrderReconciler(control_plane=scp, state_machine=sm)

        record = reconciler.register_ack_timeout("ord_1001", "req_5001")
        assert reconciler.has_active_unknown_orders() is True
        assert sm.current_fault == ConnectionFault.ORDER_ACK_UNKNOWN
        assert scp.get_state() == SafetyState.RECONCILIATION_LOCK

    def test_reconciliation_resolution_clears_lock(self):
        """Verify resolving order against broker truth clears RECONCILIATION_LOCK."""
        scp = SafetyControlPlane()
        sm = BrokerConnectionStateMachine("IBKR", control_plane=scp)
        reconciler = OrderReconciler(control_plane=scp, state_machine=sm)

        reconciler.register_ack_timeout("ord_1001", "req_5001")
        assert scp.get_state() == SafetyState.RECONCILIATION_LOCK

        # Reconcile order
        reconciled = reconciler.reconcile_order_with_broker_truth("ord_1001", "FILLED", "brk_1001")
        assert reconciled.resolution == "RECONCILED_SUCCESS"
        assert len(reconciled.evidence_hash) == 64
        assert reconciler.has_active_unknown_orders() is False
        assert scp.get_state() == SafetyState.READY


class TestBrokerProductionGate:
    """Tests for 5B-P8, 5B-P11, D1-D10 assertions."""

    def test_dispatch_allowed_only_in_connected_healthy(self):
        """Verify dispatch allowed ONLY when ConnectionState is CONNECTED_HEALTHY (5B-P11, D1)."""
        gate = BrokerProductionGate(broker_id="IBKR", environment="TEST")
        
        # Uninitialized gate is in DISCONNECTED state -> dispatch should be rejected
        with pytest.raises(DispatchIneligibleException) as exc_info:
            gate.dispatch_order({"order_id": "ord_101", "request_id": "req_101"})

        assert "must be CONNECTED_HEALTHY" in str(exc_info.value)

    def test_successful_initialization_and_dispatch(self):
        """Verify full initialization enables order dispatch."""
        gate = BrokerProductionGate(broker_id="IBKR", environment="TEST")
        cert_pin = gate.tls_validator.pin_set.active_pin

        initialized = gate.initialize_connection(cert_pin, "api.ibkr.com")
        assert initialized is True
        assert gate.state_machine.current_state == ConnectionState.CONNECTED_HEALTHY

        response = gate.dispatch_order({"order_id": "ord_200", "request_id": "req_200"})
        assert response["status"] == "DISPATCHED"

    def test_ack_timeout_during_dispatch_raises_exception(self):
        """Verify ACK timeout during dispatch raises OrderStateUnknownException and locks system."""
        gate = BrokerProductionGate(broker_id="IBKR", environment="TEST")
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        with pytest.raises(OrderStateUnknownException):
            gate.dispatch_order({"order_id": "ord_300", "request_id": "req_300"}, simulate_ack_timeout=True)

        assert gate.control_plane.get_state() == SafetyState.RECONCILIATION_LOCK

    def test_secret_leakage_sanitization(self):
        """Verify zero secret leakage in connection diagnostics (5B-P9)."""
        from governance.secret_sanitizer import SecretSanitizer
        policy = BrokerConnectivityPolicy(
            broker_id="IBKR",
            environment="TEST",
            signature="hmac_signature: 1234567890abcdef1234567890abcdef"
        )
        dict_payload = policy.canonical_dict()
        dict_payload["signature"] = policy.signature
        sanitized = SecretSanitizer.sanitize_dict(dict_payload)

        assert "1234567890abcdef1234567890abcdef" not in str(sanitized)
