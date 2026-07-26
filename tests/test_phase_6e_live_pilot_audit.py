"""
NexTrade Phase 6E — Controlled Live Pilot & Micro-Capital Execution Governance Audit Test Suite.

Verifies all 15 controlled live pilot invariants (6E-P1 through 6E-P15) with both positive
and negative / fail-closed assertions.
"""

import os
import pytest
from hardening import SafetyControlPlane, SafetyState
from pilot.live_pilot_certifier import LivePilotCertifier
from pilot.micro_capital_governance_engine import (
    MicroCapitalGovernanceEngine,
    PilotSessionState,
    MicroCapitalCeilingExceededException,
    PilotAccountIsolationException,
    MandatoryStopLossException
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase6ELivePilotAudit:
    """Test suite certifying 6E-P1 through 6E-P15 invariants."""

    def test_6e_p1_single_account_isolation(self):
        """Verify 6E-P1 single pilot account isolation guard (ACC_PILOT_MICRO_01)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p1_single_account_isolation()
        assert res["status"] == "PASS"
        assert res["bound_account"] == "ACC_PILOT_MICRO_01"
        assert res["unauthorized_account_rejected"] is True

        # Explicit negative test
        engine = MicroCapitalGovernanceEngine()
        with pytest.raises(PilotAccountIsolationException):
            engine.verify_account_isolation("ACC_UNAUTHORIZED_XYZ")

    def test_6e_p2_micro_capital_ceiling(self):
        """Verify 6E-P2 hard micro-capital exposure ceiling ($500.00 Max)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p2_micro_capital_ceiling()
        assert res["status"] == "PASS"
        assert res["within_ceiling_accepted"] is True
        assert res["ceiling_exceeded_blocked"] is True

        # Explicit negative test: allocation above ceiling ($500.01) throws exception
        engine = MicroCapitalGovernanceEngine()
        with pytest.raises(MicroCapitalCeilingExceededException):
            engine.verify_capital_ceiling(500.01)

    def test_6e_p3_position_limits_and_atomic_reservation(self):
        """Verify 6E-P3 position notional ($100 max) and max position count (2 max)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p3_position_limits_and_atomic_reservation()
        assert res["status"] == "PASS"
        assert res["max_position_notional"] == "$100.00"

        # Explicit negative test
        engine = MicroCapitalGovernanceEngine()
        with pytest.raises(MicroCapitalCeilingExceededException):
            engine.verify_position_limits("AAPL", 100.01)

    def test_6e_p4_daily_loss_limit(self):
        """Verify 6E-P4 max daily drawdown & loss limit ($50.00 Max Loss -> HARD_HALT)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p4_daily_loss_limit()
        assert res["status"] == "PASS"
        assert res["safety_state_after_breach"] == "HARD_HALT"

    def test_6e_p5_mandatory_stop_loss_requirement(self):
        """Verify 6E-P5 mandatory stop-loss requirement on live entry orders."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p5_mandatory_stop_loss_requirement()
        assert res["status"] == "PASS"
        assert res["missing_stop_loss_blocked"] is True

        # Explicit negative test
        engine = MicroCapitalGovernanceEngine()
        with pytest.raises(MandatoryStopLossException):
            engine.validate_stop_loss_attachment("ord_1", stop_loss_confirmed=False)

    def test_6e_p6_control_plane_pre_dispatch_intercept(self):
        """Verify 6E-P6 SafetyControlPlane pre-dispatch intercept & approval token."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p6_control_plane_pre_dispatch_intercept()
        assert res["status"] == "PASS"
        assert len(res["approval_token_id"]) > 0

    def test_6e_p7_automatic_fail_closed_escalation(self):
        """Verify 6E-P7 automatic fail-closed escalation matrix (HOLD, HARD_HALT)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p7_automatic_fail_closed_escalation()
        assert res["status"] == "PASS"
        assert res["hold_state_escalation"] == "HOLD"
        assert res["hard_halt_escalation"] == "HARD_HALT"

    def test_6e_p8_dual_position_reconciliation(self):
        """Verify 6E-P8 dual broker vs internal position reconciliation."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p8_dual_position_reconciliation()
        assert res["status"] == "PASS"
        assert res["mismatch_reconciliation_locked"] is True

    def test_6e_p9_hash_chained_pilot_audit_log(self):
        """Verify 6E-P9 immutable hash-chained live pilot audit logging."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p9_hash_chained_pilot_audit_log()
        assert res["status"] == "PASS"

    def test_6e_p10_margin_utilization_ceiling(self):
        """Verify 6E-P10 margin utilization ceiling monitor (20% Max -> HOLD)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p10_margin_utilization_ceiling()
        assert res["status"] == "PASS"
        assert res["margin_breach_blocked"] is True

    def test_6e_p11_live_slippage_monitor(self):
        """Verify 6E-P11 live micro-capital slippage monitor (>0.5% -> HOLD)."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p11_live_slippage_monitor()
        assert res["status"] == "PASS"

    def test_6e_p12_sub100ms_kill_switch_response(self):
        """Verify 6E-P12 sub-100ms emergency kill-switch response time."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p12_sub100ms_kill_switch_response()
        assert res["status"] == "PASS"
        assert res["total_latency_ms"] < 100.0

    def test_6e_p13_manual_operator_emergency_intercept(self):
        """Verify 6E-P13 governance operator manual intercept & session arming."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p13_manual_operator_emergency_intercept()
        assert res["status"] == "PASS"
        assert res["operator_armed"] is True

    def test_6e_p14_session_termination_and_flattening(self):
        """Verify 6E-P14 automatic pilot session termination & emergency flattening."""
        certifier = LivePilotCertifier()
        res = certifier.verify_6e_p14_session_termination_and_flattening()
        assert res["status"] == "PASS"
        assert res["session_state"] == "SESSION_TERMINATED"

    def test_6e_p15_live_pilot_manifest_generation(self):
        """Verify 6E-P15 complete controlled live pilot certification manifest generation."""
        certifier = LivePilotCertifier()
        all_passed, manifest = certifier.execute_full_6e_live_pilot_audit()
        assert all_passed is True
        assert manifest["invariants_total"] == 15
        assert manifest["invariants_passed"] == 15
        assert manifest["signing_status"] == "CERTIFICATION_SIGNING_PENDING"
        assert len(manifest["manifest_sha256"]) == 64
        assert manifest["pilot_account_id"] == "ACC_PILOT_MICRO_01"
