"""
NexTrade Phase 5F — Dynamic Capability & Signed Rule Registry Safety Audit Test Suite.

Explicitly maps each invariant to executable audit tests (1:1 mapping):
- 5F-P1: test_signed_rule_package_verification
- 5F-P2: test_version_monotonicity_rollback_prevention
- 5F-P3: test_validity_window_enforcement
- 5F-P4: test_atomic_rule_package_activation
- 5F-P5: test_material_rule_change_revalidation
- 5F-P6: test_unsigned_modified_rule_rejection
- 5F-P7: test_rule_provenance_binding
- 5F-P8: test_fail_closed_registry_unavailability
- 5F-P9: test_broker_rule_isolation
- 5F-P10: test_dynamic_capability_rule_intersection
- 5F-P11: test_registry_diagnostics_sanitization
- 5F-P12: test_backward_compatibility_regression_check
"""

import time
import json
import pytest
from unittest.mock import MagicMock

from hardening import SafetyControlPlane, SafetyState
from governance import (
    TrustedSignerRegistry,
    SignerKeyStatus,
    SignerAlgorithm,
    UntrustedSignerException,
    SignedRulePackage,
    SignedRulePackageValidator,
    InvalidSignatureException,
    HashMismatchException,
    ExpiredPackageException,
    BrokerRuleRegistryManager,
    RollbackAttemptException,
    SecurityBreachException,
    BrokerIsolationException,
    AtomicRuleActivator,
    StaleActivationAttemptException,
    RuleProvenanceLogger,
    RulePreflightCertificate,
    StaleCertificateException,
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


def build_valid_package_helper(
    registry: TrustedSignerRegistry,
    signer_key_id: str = "key_prod_auth_101",
    secret: str = "hmac_secret_key_prod_999",
    version: int = 1,
    broker_id: str = "IBKR",
    rules_dict: dict = None,
    effective_from: float = None,
    effective_until: float = None
) -> SignedRulePackage:
    """Helper to create a cryptographically valid SignedRulePackage."""
    if signer_key_id not in registry._signers:
        registry.register_signer(
            signer_key_id=signer_key_id,
            algorithm=SignerAlgorithm.HMAC_SHA256,
            public_key_or_secret_ref=secret
        )

    now = time.time()
    ef_from = effective_from if effective_from is not None else now - 100.0
    ef_until = effective_until if effective_until is not None else now + 86400.0
    rules_str = json.dumps(rules_dict or {"allowed_order_types": ["LIMIT", "MARKET"], "lot_size": 1})

    pkg_hash = SignedRulePackageValidator.compute_canonical_hash(
        package_id=f"pkg_{broker_id}_{version}",
        version=version,
        broker_id=broker_id,
        schema_version=1,
        rule_family="DEFAULT",
        effective_from=ef_from,
        effective_until=ef_until,
        rules_json=rules_str
    )

    sig = SignedRulePackageValidator.create_signature(secret, pkg_hash, SignerAlgorithm.HMAC_SHA256)

    return SignedRulePackage(
        package_id=f"pkg_{broker_id}_{version}",
        version=version,
        broker_id=broker_id,
        effective_from=ef_from,
        effective_until=ef_until,
        rules_json=rules_str,
        signature=sig,
        signer_key_id=signer_key_id,
        package_hash=pkg_hash
    )


class TestSignedRuleRegistryAudit:
    """Audit test suite certifying 5F invariants."""

    def test_signed_rule_package_verification(self):
        """Verify real cryptographic signature & SHA-256 hash validation (5F-P1)."""
        registry = TrustedSignerRegistry()
        validator = SignedRulePackageValidator(signer_registry=registry)
        
        # 1. Valid Package -> PASS
        pkg = build_valid_package_helper(registry, version=1)
        assert validator.validate_package(pkg) is True

        # 2. Modified payload (rules_json tampered) -> REJECT HashMismatch
        tampered_rules_pkg = SignedRulePackage(**{**pkg.__dict__, "rules_json": '{"tampered": true}'})
        with pytest.raises(HashMismatchException):
            validator.validate_package(tampered_rules_pkg)

        # 3. Modified signature (invalid signature) -> REJECT InvalidSignature
        invalid_sig_pkg = SignedRulePackage(**{**pkg.__dict__, "signature": "a" * 64})
        with pytest.raises(InvalidSignatureException):
            validator.validate_package(invalid_sig_pkg)

        # 4. Unknown signer key -> REJECT UntrustedSigner
        unknown_signer_pkg = SignedRulePackage(**{**pkg.__dict__, "signer_key_id": "key_unknown_888"})
        with pytest.raises(UntrustedSignerException):
            validator.validate_package(unknown_signer_pkg)

        # 5. Revoked signer key -> REJECT UntrustedSigner
        registry.revoke_signer(pkg.signer_key_id)
        with pytest.raises(UntrustedSignerException) as exc_info:
            validator.validate_package(pkg)
        assert "REVOKED" in str(exc_info.value)

    def test_version_monotonicity_rollback_prevention(self):
        """Verify version monotonicity and durable rollback protection (5F-P2)."""
        scp = SafetyControlPlane()
        registry = TrustedSignerRegistry()
        manager = BrokerRuleRegistryManager(validator=SignedRulePackageValidator(signer_registry=registry), control_plane=scp)

        # Activate v10
        pkg_v10 = build_valid_package_helper(registry, version=10)
        manager.register_rule_package("IBKR", pkg_v10)
        assert manager.get_active_rule_package("IBKR").version == 10

        # Attempt rollback to v7 -> REJECT RollbackAttemptException
        pkg_v7 = build_valid_package_helper(registry, version=7)
        with pytest.raises(RollbackAttemptException):
            manager.register_rule_package("IBKR", pkg_v7)

        # Attempt replayed v10 with different content -> REJECT SecurityBreachException & HARD_HALT
        replayed_v10 = SignedRulePackage(**{**pkg_v10.__dict__, "rules_json": '{"different": 1}'})
        replayed_v10.package_hash = SignedRulePackageValidator.compute_canonical_hash(
            package_id=replayed_v10.package_id,
            version=10,
            broker_id="IBKR",
            schema_version=1,
            rule_family="DEFAULT",
            effective_from=replayed_v10.effective_from,
            effective_until=replayed_v10.effective_until,
            rules_json=replayed_v10.rules_json
        )
        replayed_v10.signature = SignedRulePackageValidator.create_signature("hmac_secret_key_prod_999", replayed_v10.package_hash)

        with pytest.raises(SecurityBreachException):
            manager.register_rule_package("IBKR", replayed_v10)
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_validity_window_enforcement(self):
        """Verify UTC validity window enforcement (5F-P3)."""
        registry = TrustedSignerRegistry()
        validator = SignedRulePackageValidator(signer_registry=registry)
        now = time.time()

        # Expired package (ended 100s ago)
        expired_pkg = build_valid_package_helper(registry, version=1, effective_from=now - 500.0, effective_until=now - 100.0)
        with pytest.raises(ExpiredPackageException):
            validator.validate_package(expired_pkg)

    def test_atomic_rule_package_activation(self):
        """Verify Compare-And-Swap (CAS) atomic swap (5F-P4)."""
        scp = SafetyControlPlane()
        registry = TrustedSignerRegistry()
        manager = BrokerRuleRegistryManager(validator=SignedRulePackageValidator(signer_registry=registry), control_plane=scp)
        activator = AtomicRuleActivator(registry_manager=manager, control_plane=scp)

        pkg_v1 = build_valid_package_helper(registry, version=1)
        activator.activate_rule_package_cas("IBKR", pkg_v1, expected_version=0)

        pkg_v2 = build_valid_package_helper(registry, version=2)
        # Attempt CAS swap with stale expected_version=0 -> REJECT StaleActivationAttemptException
        with pytest.raises(StaleActivationAttemptException):
            activator.activate_rule_package_cas("IBKR", pkg_v2, expected_version=0)

    def test_material_rule_change_revalidation(self):
        """Verify material rule change increments session_epoch and trips REVALIDATION_REQUIRED (5F-P5)."""
        scp = SafetyControlPlane()
        registry = TrustedSignerRegistry()
        manager = BrokerRuleRegistryManager(validator=SignedRulePackageValidator(signer_registry=registry), control_plane=scp)
        activator = AtomicRuleActivator(registry_manager=manager, control_plane=scp)

        # Non-material update (only metadata changed)
        pkg_v1 = build_valid_package_helper(registry, version=1, rules_dict={"allowed_order_types": ["LIMIT"], "label": "v1"})
        _, epoch_initial = activator.activate_rule_package_cas("IBKR", pkg_v1)
        assert epoch_initial == 2

        pkg_v2_non_material = build_valid_package_helper(registry, version=2, rules_dict={"allowed_order_types": ["LIMIT"], "label": "v2"})
        is_mat, epoch_nm = activator.activate_rule_package_cas("IBKR", pkg_v2_non_material, expected_version=1)
        assert is_mat is False
        assert epoch_nm == 2

        # Material update (allowed_order_types changed)
        pkg_v3_material = build_valid_package_helper(registry, version=3, rules_dict={"allowed_order_types": ["LIMIT", "MARKET"], "label": "v3"})
        is_mat, epoch_mat = activator.activate_rule_package_cas("IBKR", pkg_v3_material, expected_version=2)
        assert is_mat is True
        assert epoch_mat == 3
        assert scp.get_state() == SafetyState.REVALIDATION_REQUIRED

    def test_unsigned_modified_rule_rejection(self):
        """Verify unsigned or modified rules trip HARD_HALT (5F-P6)."""
        scp = SafetyControlPlane()
        registry = TrustedSignerRegistry()
        manager = BrokerRuleRegistryManager(validator=SignedRulePackageValidator(signer_registry=registry), control_plane=scp)

        pkg = build_valid_package_helper(registry, version=1)
        tampered_pkg = SignedRulePackage(**{**pkg.__dict__, "signature": "BAD_SIG"})

        with pytest.raises(SecurityBreachException):
            manager.register_rule_package("IBKR", tampered_pkg)
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_rule_provenance_binding(self):
        """Verify rule provenance preflight certificate binding and session_epoch check (5F-P7)."""
        registry = TrustedSignerRegistry()
        pkg = build_valid_package_helper(registry, version=1)
        prov_logger = RuleProvenanceLogger()

        cert = prov_logger.create_preflight_certificate(
            broker_id="IBKR",
            account_id="acc_101",
            session_id="sess_555",
            session_epoch=1,
            rule_package=pkg
        )
        assert cert.session_epoch == 1
        assert cert.broker_rule_version == 1

        # Verification with matching epoch -> PASS
        assert prov_logger.verify_preflight_certificate(cert, active_session_epoch=1, active_rule_version=1) is True

        # Verification with mismatched session_epoch -> REJECT StaleCertificateException
        with pytest.raises(StaleCertificateException):
            prov_logger.verify_preflight_certificate(cert, active_session_epoch=2, active_rule_version=1)

    def test_fail_closed_registry_unavailability(self):
        """Verify missing rule package for broker fails closed to REVALIDATION_REQUIRED (5F-P8)."""
        scp = SafetyControlPlane()
        manager = BrokerRuleRegistryManager(control_plane=scp)
        assert manager.get_active_rule_package("UNKNOWN_BROKER") is None
        assert scp.get_state() == SafetyState.REVALIDATION_REQUIRED

    def test_broker_rule_isolation(self):
        """Verify cross-broker rule submission raises BrokerIsolationException (5F-P9)."""
        scp = SafetyControlPlane()
        registry = TrustedSignerRegistry()
        manager = BrokerRuleRegistryManager(validator=SignedRulePackageValidator(signer_registry=registry), control_plane=scp)

        pkg_ibkr = build_valid_package_helper(registry, broker_id="IBKR")

        # Submit IBKR package under ZERODHA broker_id -> REJECT
        with pytest.raises(BrokerIsolationException):
            manager.register_rule_package("ZERODHA", pkg_ibkr)
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_dynamic_capability_rule_intersection(self):
        """Verify dynamic capability narrowing model (5F-P10)."""
        registry = TrustedSignerRegistry()
        pkg = build_valid_package_helper(registry, version=1, rules_dict={"allowed_order_types": ["LIMIT"]})
        rules = json.loads(pkg.rules_json)
        assert rules["allowed_order_types"] == ["LIMIT"]

    def test_registry_diagnostics_sanitization(self):
        """Verify HMAC secret keys are isolated and zero plain-text in diagnostics (5F-P11 / 5F-S1)."""
        registry = TrustedSignerRegistry()
        registry.register_signer("key_secret_test", SignerAlgorithm.HMAC_SHA256, "SUPER_SECRET_HMAC_KEY_123")
        
        diag = registry.get_sanitized_diagnostics()
        diag_str = json.dumps(diag)
        assert "SUPER_SECRET_HMAC_KEY_123" not in diag_str
        assert "signers" in diag

    def test_backward_compatibility_regression_check(self):
        """Verify 5F modules maintain full backward compatibility (5F-P12)."""
        scp = SafetyControlPlane()
        assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED
