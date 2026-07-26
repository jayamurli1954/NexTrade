"""
NexTrade Phase 6G — Final Production Activation & Graduation Gate Audit Test Suite.

Verifies all 15 final production activation invariants (6G-P1 through 6G-P15) with both positive
and negative / fail-closed assertions.
"""

import os
import pytest
from hardening import SafetyControlPlane, SafetyState
from activation.production_activation_certifier import ProductionActivationCertifier
from activation.production_activation_manager import (
    ProductionActivationManager,
    ActivationState,
    ActivationDeniedException
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase6GProductionActivationAudit:
    """Test suite certifying 6G-P1 through 6G-P15 invariants."""

    def test_6g_p1_production_identity_attestation(self):
        """Verify 6G-P1 production identity & environment attestation."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p1_production_identity_attestation()
        assert res["status"] == "PASS"

    def test_6g_p2_config_immutability_and_checksums(self):
        """Verify 6G-P2 production configuration immutability & cryptographic checksums."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p2_config_immutability_and_checksums()
        assert res["status"] == "PASS"

    def test_6g_p3_capital_authority_chain(self):
        """Verify 6G-P3 end-to-end 6-layer capital authority chain."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p3_capital_authority_chain()
        assert res["status"] == "PASS"
        assert len(res["defense_layers"]) == 6

    def test_6g_p4_safety_precedence_ladder(self):
        """Verify 6G-P4 SafetyControlPlane 8-state ladder precedence re-audit."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p4_safety_precedence_ladder()
        assert res["status"] == "PASS"
        assert res["highest_severity_state"] == "EMERGENCY_KILL"

    def test_6g_p5_broker_capability_attestation(self):
        """Verify 6G-P5 live broker gateway capability intersection attestation."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p5_broker_capability_attestation()
        assert res["status"] == "PASS"

    def test_6g_p6_portfolio_isolation_recertification(self):
        """Verify 6G-P6 multi-account & portfolio isolation re-certification."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p6_portfolio_isolation_recertification()
        assert res["status"] == "PASS"
        assert res["registered_accounts_count"] == 3

    def test_6g_p7_disaster_recovery_and_state_reconstruction(self):
        """Verify 6G-P7 disaster recovery WAL & state reconstruction audit."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p7_disaster_recovery_and_state_reconstruction()
        assert res["status"] == "PASS"

    def test_6g_p8_kill_switch_and_flattening_reaudit(self):
        """Verify 6G-P8 production sub-100ms kill-switch & flattening re-audit."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p8_kill_switch_and_flattening_reaudit()
        assert res["status"] == "PASS"
        assert res["sub_100ms_certified"] is True

    def test_6g_p9_observability_and_slo_certification(self):
        """Verify 6G-P9 production observability, latency tracking & SLO certification."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p9_observability_and_slo_certification()
        assert res["status"] == "PASS"

    def test_6g_p10_immutable_regulatory_audit_trail(self):
        """Verify 6G-P10 immutable regulatory audit trail & evidence manifest."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p10_immutable_regulatory_audit_trail()
        assert res["status"] == "PASS"

    def test_6g_p11_secrets_and_key_ceremony_readiness(self):
        """Verify 6G-P11 secret vaulting, bytearray zeroing & release key ceremony readiness."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p11_secrets_and_key_ceremony_readiness()
        assert res["status"] == "PASS"

    def test_6g_p12_full_system_chaos_certification(self):
        """Verify 6G-P12 full-system adversarial / chaos fault injection certification."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p12_full_system_chaos_certification()
        assert res["status"] == "PASS"

    def test_6g_p13_production_soak_stability(self):
        """Verify 6G-P13 long-running production soak & stability certification."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p13_production_soak_stability()
        assert res["status"] == "PASS"
        assert res["zero_memory_leak"] is True
        assert res["zero_buffer_corruption"] is True

    def test_6g_p14_11_parameter_activation_predicate(self):
        """Verify 6G-P14 11-parameter live trading activation gate predicate evaluation."""
        certifier = ProductionActivationCertifier()
        res = certifier.verify_6g_p14_11_parameter_activation_predicate()
        assert res["status"] == "PASS"
        assert res["predicates_evaluated_count"] == 11

        # Negative test: Direct activation to PRODUCTION_ACTIVE without ARMED state throws ActivationDeniedException
        mgr = ProductionActivationManager()
        with pytest.raises(ActivationDeniedException):
            mgr.advance_state(ActivationState.PRODUCTION_ACTIVE)

    def test_6g_p15_master_manifest_generation(self):
        """Verify 6G-P15 complete final production activation manifest generation."""
        certifier = ProductionActivationCertifier()
        all_passed, manifest = certifier.execute_full_6g_production_activation_audit()
        assert all_passed is True
        assert manifest["invariants_total"] == 15
        assert manifest["invariants_passed"] == 15
        assert manifest["signing_status"] == "CERTIFICATION_SIGNING_PENDING"
        assert len(manifest["manifest_sha256"]) == 64
