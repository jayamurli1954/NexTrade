"""
NexTrade Phase 6F — Multi-Account Graduation & Portfolio Isolation Governance Audit Test Suite.

Verifies all 15 multi-account graduation invariants (6F-P1 through 6F-P15) with both positive
and negative / fail-closed assertions.
"""

import os
import pytest
from hardening import SafetyControlPlane, SafetyState
from governance.multi_account_certifier import MultiAccountCertifier
from governance.multi_account_portfolio_manager import (
    MultiAccountPortfolioManager,
    AccountState,
    CrossAccountLeakageException,
    PortfolioCeilingExceededException,
    AccountHaltedException
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase6FMultiAccountAudit:
    """Test suite certifying 6F-P1 through 6F-P15 invariants."""

    def test_6f_p1_multi_account_registry(self):
        """Verify 6F-P1 multi-account registry & cryptographic identity binding."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p1_multi_account_registry()
        assert res["status"] == "PASS"
        assert res["unauthorized_account_blocked"] is True

        # Negative test: unauthorized account ID throws CrossAccountLeakageException
        mgr = MultiAccountPortfolioManager()
        with pytest.raises(CrossAccountLeakageException):
            mgr.verify_account_registration("ACC_UNAUTHORIZED_ACCOUNT_99")

    def test_6f_p2_zero_cross_account_leakage(self):
        """Verify 6F-P2 zero cross-account leakage guard."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p2_zero_cross_account_leakage()
        assert res["status"] == "PASS"
        assert res["cross_account_leakage_blocked"] is True

        # Negative test: Account 1 accessing Account 2 throws CrossAccountLeakageException
        mgr = MultiAccountPortfolioManager()
        with pytest.raises(CrossAccountLeakageException):
            mgr.verify_zero_cross_account_leakage("ACC_PROD_MULTI_01", "ACC_PROD_MULTI_02")

    def test_6f_p3_per_account_risk_envelopes(self):
        """Verify 6F-P3 per-account capital ($1,000) & daily loss ($100) envelopes."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p3_per_account_risk_envelopes()
        assert res["status"] == "PASS"
        assert res["daily_loss_breach_halted"] is True

    def test_6f_p4_portfolio_aggregate_ceiling(self):
        """Verify 6F-P4 portfolio aggregate exposure ceiling ($3,000 Max Total Exposure)."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p4_portfolio_aggregate_ceiling()
        assert res["status"] == "PASS"
        assert res["portfolio_ceiling_blocked"] is True

        # Negative test: allocation over portfolio ceiling ($3,001) throws exception
        mgr = MultiAccountPortfolioManager()
        with pytest.raises(PortfolioCeilingExceededException):
            mgr.verify_and_reserve_atomic_exposure("ACC_PROD_MULTI_01", "intent_over_port", "AAPL", 3001.0)

    def test_6f_p5_atomic_dual_scope_reservation(self):
        """Verify 6F-P5 / 6F-P5A atomic dual-scope cross-account position reservation."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p5_atomic_dual_scope_reservation()
        assert res["status"] == "PASS"
        assert res["account_1_exposure"] == 500.0
        assert res["portfolio_aggregate_exposure"] == 1000.0

    def test_6f_p6_account_level_reconciliation(self):
        """Verify 6F-P6 account-level dual position reconciliation."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p6_account_level_reconciliation()
        assert res["status"] == "PASS"
        assert res["mismatch_locked"] is True

    def test_6f_p7_portfolio_aggregate_reconciliation(self):
        """Verify 6F-P7 portfolio-level aggregate reconciliation across all accounts."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p7_portfolio_aggregate_reconciliation()
        assert res["status"] == "PASS"
        assert res["portfolio_reconciled_all"] is True

    def test_6f_p8_account_capability_intercept(self):
        """Verify 6F-P8 account-specific broker capability intercept."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p8_account_capability_intercept()
        assert res["status"] == "PASS"
        assert res["unsupported_capability_blocked"] is True

    def test_6f_p9_hierarchical_kill_switch(self):
        """Verify 6F-P9 hierarchical kill-switch matrix (account-scoped vs master portfolio kill)."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p9_hierarchical_kill_switch()
        assert res["status"] == "PASS"
        assert res["account_scoped_kill_verified"] is True
        assert res["portfolio_master_kill_verified"] is True

    def test_6f_p10_account_failure_isolation(self):
        """Verify 6F-P10 account failure isolation guard (Account A failure does not halt Account B)."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p10_account_failure_isolation()
        assert res["status"] == "PASS"
        assert res["failed_account_isolated"] is True
        assert res["healthy_account_active"] is True

    def test_6f_p11_preflight_session_epoch_binding(self):
        """Verify 6F-P11 account preflight session epoch & package hash binding."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p11_preflight_session_epoch_binding()
        assert res["status"] == "PASS"
        assert res["preflight_valid"] is True

    def test_6f_p12_portfolio_margin_utilization(self):
        """Verify 6F-P12 portfolio aggregate margin utilization monitor (30% Max -> HOLD)."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p12_portfolio_margin_utilization()
        assert res["status"] == "PASS"
        assert res["margin_breach_blocked"] is True

    def test_6f_p13_multi_account_emergency_flattening(self):
        """Verify 6F-P13 multi-account emergency position flattening."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6e_p13_multi_account_emergency_flattening()
        assert res["status"] == "PASS"
        assert res["total_positions_flattened"] == 2
        assert res["all_accounts_killed"] is True

    def test_6f_p14_multi_tenant_audit_stream(self):
        """Verify 6F-P14 multi-tenant tamper-evident audit stream with account_id correlation tags."""
        certifier = MultiAccountCertifier()
        res = certifier.verify_6f_p14_multi_tenant_audit_stream()
        assert res["status"] == "PASS"
        assert res["account_tag_verified"] is True

    def test_6f_p15_multi_account_manifest_generation(self):
        """Verify 6F-P15 complete multi-account graduation certification manifest generation."""
        certifier = MultiAccountCertifier()
        all_passed, manifest = certifier.execute_full_6f_multi_account_audit()
        assert all_passed is True
        assert manifest["invariants_total"] == 15
        assert manifest["invariants_passed"] == 15
        assert manifest["signing_status"] == "CERTIFICATION_SIGNING_PENDING"
        assert len(manifest["manifest_sha256"]) == 64
        assert manifest["portfolio_aggregate_ceiling"] == "$3,000.00"
