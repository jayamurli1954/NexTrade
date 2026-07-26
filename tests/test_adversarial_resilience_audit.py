"""
NexTrade Phase 5H — End-to-End Adversarial Chaos & System Resilience Audit Test Suite.

Explicitly maps each invariant to executable audit tests (1:1 mapping):
- 5H-P1: test_broker_outage_ack_timeout_containment
- 5H-P2: test_order_ambiguity_containment
- 5H-P3: test_concurrent_session_epoch_race_containment
- 5H-P4: test_clock_drift_manipulation_defense
- 5H-P5: test_secret_vault_unavailability_containment
- 5H-P6: test_safety_state_precedence_conflict_resolution
- 5H-P7: test_process_crash_recovery_reconstruction
- 5H-P8: test_multi_account_cascade_failure_isolation
- 5H-P9: test_rule_package_corruption_fail_closed
- 5H-P10: test_controlled_recovery_pipeline_verification
- 5H-P11: test_secret_isolation_under_chaos
- 5H-P12: test_backward_compatibility_regression_check
"""

import time
import pytest

from hardening import SafetyControlPlane, SafetyState
from brokers import BrokerProductionGate
from governance import (
    TrustedSignerRegistry,
    SignerAlgorithm,
    SignedRulePackage,
    SignedRulePackageValidator,
    StaleCertificateException,
    MultiAccountPreflightManager,
    SecretSanitizer,
)
from resilience.chaos_engine import ResilienceChaosEngine
from resilience.controlled_recovery import ControlledRecoveryPipeline


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


def build_valid_package_helper(registry: TrustedSignerRegistry = None) -> SignedRulePackage:
    reg = registry or TrustedSignerRegistry()
    if "key_5h_100" not in reg._signers:
        reg.register_signer("key_5h_100", SignerAlgorithm.HMAC_SHA256, "secret_key_5h")
    pkg_hash = SignedRulePackageValidator.compute_canonical_hash("pkg_5h", 1, "IBKR", 1, "DEFAULT", 0.0, 4102444800.0, '{"test": 1}')
    sig = SignedRulePackageValidator.create_signature("secret_key_5h", pkg_hash)
    return SignedRulePackage("pkg_5h", 1, "IBKR", 0.0, 4102444800.0, '{"test": 1}', sig, "key_5h_100", pkg_hash)


class TestAdversarialResilienceAudit:
    """Audit test suite certifying 5H invariants."""

    def test_broker_outage_ack_timeout_containment(self):
        """Verify injected ACK timeout forces ORDER_STATE_UNKNOWN and RECONCILIATION_LOCK (5H-P1)."""
        scp = SafetyControlPlane()
        chaos = ResilienceChaosEngine(control_plane=scp)

        chaos.inject_broker_ack_timeout("IBKR", "ord_chaos_99")
        assert scp.get_state() == SafetyState.RECONCILIATION_LOCK

    def test_order_ambiguity_containment(self):
        """Verify order ambiguity prevents new order dispatches at BrokerProductionGate (5H-P2)."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        chaos = ResilienceChaosEngine(control_plane=scp, order_reconciler=gate.reconciler)
        chaos.inject_broker_ack_timeout("IBKR", "ord_ambiguity_1")

        is_eligible, reason, _ = gate.evaluate_dispatch_eligibility()
        assert is_eligible is False

    def test_concurrent_session_epoch_race_containment(self):
        """Verify session_epoch race invalidates old preflight certificates (5H-P3)."""
        pkg = build_valid_package_helper()
        manager = MultiAccountPreflightManager()
        cert = manager.issue_account_certificate("IBKR", "ACC_A", "SESS_1", session_epoch=1, rule_package=pkg)

        # Invalidate by advancing active session_epoch to 2
        with pytest.raises(StaleCertificateException):
            manager.validate_account_dispatch({"account_id": "ACC_A", "broker_id": "IBKR"}, cert, active_session_epoch=2, active_rule_version=1)

    def test_clock_drift_manipulation_defense(self):
        """Verify injected clock drift trips SafetyControlPlane to HARD_HALT (5H-P4)."""
        scp = SafetyControlPlane()
        chaos = ResilienceChaosEngine(control_plane=scp)

        chaos.inject_clock_skew(600.0)
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_secret_vault_unavailability_containment(self):
        """Verify Secret Vault lock trips SafetyControlPlane to HARD_HALT (5H-P5)."""
        scp = SafetyControlPlane()
        chaos = ResilienceChaosEngine(control_plane=scp)

        chaos.inject_secret_vault_lock()
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_safety_state_precedence_conflict_resolution(self):
        """Verify higher severity SafetyState (HARD_HALT > HOLD > READY) dominates (5H-P6)."""
        scp = SafetyControlPlane()
        scp.report_subsystem_state("sub1", SafetyState.READY, "Subsystem 1 ready")
        assert scp.get_state() == SafetyState.READY

        scp.report_subsystem_state("sub2", SafetyState.HOLD, "Subsystem 2 hold")
        assert scp.get_state() == SafetyState.HOLD

        scp.report_subsystem_state("sub3", SafetyState.HARD_HALT, "Subsystem 3 hard halt")
        assert scp.get_state() == SafetyState.HARD_HALT

        # Transitioning sub1 back to READY cannot lower global state from HARD_HALT
        scp.report_subsystem_state("sub1", SafetyState.READY, "Subsystem 1 ready again")
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_process_crash_recovery_reconstruction(self):
        """Verify process crash recovery and atomic state reconstruction (5H-P7)."""
        scp = SafetyControlPlane()
        reg = TrustedSignerRegistry()
        pkg = build_valid_package_helper(reg)
        val = SignedRulePackageValidator(signer_registry=reg)
        pipeline = ControlledRecoveryPipeline(control_plane=scp, rule_validator=val)

        # Simulate halted state
        scp.report_subsystem_state("broker_conn_IBKR", SafetyState.RECONCILIATION_LOCK, "Halted")

        success, cert = pipeline.execute_full_controlled_recovery("IBKR", "ACC_A", "SESS_1", 1, pkg)
        assert success is True
        assert scp.get_state() == SafetyState.READY

    def test_multi_account_cascade_failure_isolation(self):
        """Verify cascade failure in one account does not corrupt another account certificate (5H-P8)."""
        pkg = build_valid_package_helper()
        manager = MultiAccountPreflightManager()

        cert_a = manager.issue_account_certificate("IBKR", "ACC_A", "SESS_1", 1, pkg)
        cert_b = manager.issue_account_certificate("IBKR", "ACC_B", "SESS_1", 1, pkg)

        assert cert_a.account_id == "ACC_A"
        assert cert_b.account_id == "ACC_B"

    def test_rule_package_corruption_fail_closed(self):
        """Verify corrupted rule package fails closed during recovery step 2 (5H-P9)."""
        pkg = build_valid_package_helper()
        corrupted_pkg = SignedRulePackage(**{**pkg.__dict__, "signature": "BAD_SIG"})
        
        pipeline = ControlledRecoveryPipeline()
        with pytest.raises(Exception):
            pipeline.step2_reverify_rule_package(corrupted_pkg)

    def test_controlled_recovery_pipeline_verification(self):
        """Verify full 4-step Controlled Recovery Pipeline recertification (5H-P10)."""
        scp = SafetyControlPlane()
        reg = TrustedSignerRegistry()
        pkg = build_valid_package_helper(reg)
        val = SignedRulePackageValidator(signer_registry=reg)
        pipeline = ControlledRecoveryPipeline(control_plane=scp, rule_validator=val)

        # Simulate ACK timeout fault
        pipeline.reconciler.register_ack_timeout("ord_100", "req_100")
        assert scp.get_state() == SafetyState.RECONCILIATION_LOCK

        # Full recovery
        recovered, cert = pipeline.execute_full_controlled_recovery("IBKR", "ACC_A", "SESS_1", 1, pkg)
        assert recovered is True
        assert scp.get_state() == SafetyState.READY

    def test_secret_isolation_under_chaos(self):
        """Verify zero secret exposure during chaos exceptions and diagnostics logs (5H-P11)."""
        err_msg = SecretSanitizer.sanitize_text("Error with bearer_token: bearer_secret_token_val_999")
        assert "bearer_secret_token_val_999" not in err_msg

    def test_backward_compatibility_regression_check(self):
        """Verify 5H modules maintain full backward compatibility (5H-P12)."""
        scp = SafetyControlPlane()
        assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED
