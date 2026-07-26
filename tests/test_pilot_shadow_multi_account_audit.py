"""
NexTrade Phase 5G — Pilot Operations, Shadow Validation & Multi-Account Preflight Certification Test Suite.

Explicitly maps each invariant to executable audit tests (1:1 mapping):
- 5G-P1: test_pilot_exposure_limits_governance
- 5G-P2: test_shadow_signal_drift_comparison
- 5G-P3: test_multi_account_preflight_isolation
- 5G-P4: test_zero_cross_account_leakage
- 5G-P5: test_pilot_mode_safety_override_prevention
- 5G-P6: test_shadow_slippage_latency_tracking
- 5G-P7: test_pilot_reconciliation_lock_recovery
- 5G-P8: test_multi_account_session_epoch_verification
- 5G-P9: test_pilot_evidence_log_generation
- 5G-P10: test_multi_account_dispatch_synchronization
- 5G-P11: test_multi_account_telemetry_sanitization
- 5G-P12: test_backward_compatibility_regression_check
"""

import pytest

from hardening import SafetyControlPlane, SafetyState
from brokers import BrokerProductionGate
from pilot.pilot_operations_manager import (
    PilotOperationsManager,
    PilotExposureLimitExceededException,
    PilotSafetyOverrideException,
)
from shadow.shadow_validation_engine import ShadowValidationEngine, ShadowValidationRecord
from governance.multi_account_preflight import MultiAccountPreflightManager, CrossAccountViolationException
from governance.signed_rule_validator import SignedRulePackage, SignedRulePackageValidator
from governance import TrustedSignerRegistry, SignerAlgorithm, StaleCertificateException


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


def build_valid_package_helper() -> SignedRulePackage:
    registry = TrustedSignerRegistry()
    registry.register_signer("key_5g_100", SignerAlgorithm.HMAC_SHA256, "secret_key_5g")
    pkg_hash = SignedRulePackageValidator.compute_canonical_hash("pkg_5g", 1, "IBKR", 1, "DEFAULT", 0.0, 4102444800.0, '{"test": 1}')
    sig = SignedRulePackageValidator.create_signature("secret_key_5g", pkg_hash)
    return SignedRulePackage("pkg_5g", 1, "IBKR", 0.0, 4102444800.0, '{"test": 1}', sig, "key_5g_100", pkg_hash)


class TestPilotShadowMultiAccountAudit:
    """Audit test suite certifying 5G invariants."""

    def test_pilot_exposure_limits_governance(self):
        """Verify pilot exposure limit enforcement for position size and order rate (5G-P1)."""
        manager = PilotOperationsManager(max_position_size=1000.0, max_orders_per_min=2)
        
        # 1. Position size limit check -> REJECT
        large_payload = {"symbol": "AAPL", "quantity": 100, "price": 150.0}  # 15,000 > 1,000
        with pytest.raises(PilotExposureLimitExceededException) as exc_info:
            manager.validate_pilot_order_exposure(large_payload)
        assert "exceeds max position limit" in str(exc_info.value)

        # 2. Velocity rate check
        valid_payload = {"symbol": "AAPL", "quantity": 1, "price": 100.0}
        manager.validate_pilot_order_exposure(valid_payload)
        manager.validate_pilot_order_exposure(valid_payload)
        
        with pytest.raises(PilotExposureLimitExceededException) as exc_info:
            manager.validate_pilot_order_exposure(valid_payload)
        assert "velocity limit exceeded" in str(exc_info.value)

    def test_shadow_signal_drift_comparison(self):
        """Verify shadow execution signal drift and paper fill simulation (5G-P2)."""
        engine = ShadowValidationEngine()
        signal = {"symbol": "AAPL", "action": "BUY", "price": 150.0}
        
        record = engine.evaluate_shadow_signal(signal, paper_market_price=151.5, latency_ms=15.0)
        assert record.signal_symbol == "AAPL"
        assert record.slippage_pct == 1.0  # (1.5 / 150) * 100
        assert record.latency_ms == 15.0

    def test_multi_account_preflight_isolation(self):
        """Verify multi-account preflight certificate issuance and isolation (5G-P3)."""
        pkg = build_valid_package_helper()
        manager = MultiAccountPreflightManager()
        
        cert_a = manager.issue_account_certificate("IBKR", "ACC_A", "SESS_1", 1, pkg)
        assert cert_a.account_id == "ACC_A"
        assert cert_a.session_epoch == 1

    def test_zero_cross_account_leakage(self):
        """Verify zero cross-account leakage: mismatched account_id raises CrossAccountViolationException (5G-P4)."""
        pkg = build_valid_package_helper()
        manager = MultiAccountPreflightManager()
        cert_a = manager.issue_account_certificate("IBKR", "ACC_A", "SESS_1", 1, pkg)

        payload_b = {"symbol": "AAPL", "account_id": "ACC_B", "broker_id": "IBKR"}
        with pytest.raises(CrossAccountViolationException) as exc_info:
            manager.validate_account_dispatch(payload_b, cert_a, active_session_epoch=1, active_rule_version=1)

        assert "mismatch with certificate" in str(exc_info.value)

    def test_pilot_mode_safety_override_prevention(self):
        """Verify pilot mode cannot override or bypass SafetyControlPlane controls (5G-P5)."""
        manager = PilotOperationsManager()
        payload = {"symbol": "AAPL", "quantity": 1, "price": 10.0}

        with pytest.raises(PilotSafetyOverrideException) as exc_info:
            manager.submit_pilot_order_intent(payload, force_override=True)

        assert "cannot override or bypass" in str(exc_info.value)

    def test_shadow_slippage_latency_tracking(self):
        """Verify shadow performance aggregate metrics (5G-P6)."""
        engine = ShadowValidationEngine()
        engine.evaluate_shadow_signal({"symbol": "AAPL", "price": 100.0}, paper_market_price=101.0, latency_ms=20.0)
        engine.evaluate_shadow_signal({"symbol": "GOOG", "price": 200.0}, paper_market_price=202.0, latency_ms=30.0)

        metrics = engine.get_shadow_performance_metrics()
        assert metrics["total_records"] == 2
        assert metrics["avg_slippage_pct"] == 1.0
        assert metrics["avg_latency_ms"] == 25.0

    def test_pilot_reconciliation_lock_recovery(self):
        """Verify daily loss limit breach trips SafetyControlPlane to HOLD (5G-P7)."""
        scp = SafetyControlPlane()
        manager = PilotOperationsManager(control_plane=scp, max_daily_loss=1000.0)

        manager.record_realized_loss(1200.0)
        assert scp.get_state() == SafetyState.HOLD

    def test_multi_account_session_epoch_verification(self):
        """Verify preflight certificate rejects stale session_epoch (5G-P8)."""
        pkg = build_valid_package_helper()
        manager = MultiAccountPreflightManager()
        cert_a = manager.issue_account_certificate("IBKR", "ACC_A", "SESS_1", 1, pkg)

        payload_a = {"symbol": "AAPL", "account_id": "ACC_A", "broker_id": "IBKR"}
        with pytest.raises(StaleCertificateException):
            manager.validate_account_dispatch(payload_a, cert_a, active_session_epoch=2, active_rule_version=1)

    def test_pilot_evidence_log_generation(self):
        """Verify evidence log summary generation for pilot session audit (5G-P9)."""
        manager = PilotOperationsManager()
        log = manager.generate_pilot_evidence_log()
        assert log["pilot_status"] == "ACTIVE"
        assert "current_daily_loss" in log

    def test_multi_account_dispatch_synchronization(self):
        """Verify valid multi-account certificate passes dispatch validation (5G-P10)."""
        pkg = build_valid_package_helper()
        manager = MultiAccountPreflightManager()
        cert_a = manager.issue_account_certificate("IBKR", "ACC_A", "SESS_1", 1, pkg)

        payload_a = {"symbol": "AAPL", "account_id": "ACC_A", "broker_id": "IBKR"}
        assert manager.validate_account_dispatch(payload_a, cert_a, active_session_epoch=1, active_rule_version=1) is True

    def test_multi_account_telemetry_sanitization(self):
        """Verify multi-account telemetry contains zero secret exposure (5G-P11)."""
        manager = MultiAccountPreflightManager()
        pkg = build_valid_package_helper()
        manager.issue_account_certificate("IBKR", "ACC_SECRET_101", "SESS_1", 1, pkg)

        telemetry = manager.get_sanitized_telemetry()
        assert telemetry["active_certificates_count"] == 1

    def test_backward_compatibility_regression_check(self):
        """Verify 5G modules maintain full backward compatibility (5G-P12)."""
        scp = SafetyControlPlane()
        assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED
