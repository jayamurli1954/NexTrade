"""
NexTrade Phase 6D — Shadow Production Execution & Parallel Drift Audit Test Suite.

Verifies all 15 shadow production invariants (6D-P1 through 6D-P15) with both positive
and negative / fail-closed assertions.
"""

import os
import pytest
from hardening import SafetyControlPlane, SafetyState
from shadow.shadow_execution_certifier import ShadowExecutionCertifier
from shadow.shadow_validation_engine import ShadowValidationEngine, ZeroCapitalViolationException


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase6DShadowProductionAudit:
    """Test suite certifying 6D-P1 through 6D-P15 invariants."""

    def test_6d_p1_live_market_data_ingestion(self):
        """Verify 6D-P1 live market data ingestion & tick processing."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p1_live_market_data_ingestion()
        assert res["status"] == "PASS"
        assert res["invariant_id"] == "6D-P1"

    def test_6d_p2_zero_capital_guard(self):
        """Verify 6D-P2 zero-capital guard ($0.00) and live capital dispatch prevention."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p2_zero_capital_guard()
        assert res["status"] == "PASS"
        assert res["zero_capital_accepted"] is True
        assert res["live_capital_dispatch_blocked"] is True

        # Explicit negative test: ZeroCapitalViolationException raised on live capital dispatch attempt
        engine = ShadowValidationEngine()
        with pytest.raises(ZeroCapitalViolationException):
            engine.verify_zero_capital_guard(50.0)

    def test_6d_p3_parallel_dual_path_execution(self):
        """Verify 6D-P3 parallel paper & shadow simulated dual-path execution."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p3_parallel_dual_path_execution()
        assert res["status"] == "PASS"

    def test_6d_p4_strategy_signal_parity(self):
        """Verify 6D-P4 strategy signal parity & divergence audit."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p4_strategy_signal_parity()
        assert res["status"] == "PASS"
        assert res["parity_verified"] is True

    def test_6d_p5_order_intent_parameter_parity(self):
        """Verify 6D-P5 5-parameter order intent parity (symbol, side, qty, type, price)."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p5_order_intent_parameter_parity()
        assert res["status"] == "PASS"
        assert res["discrepancies_count"] == 0

        # Negative test: detect parameter discrepancy
        engine = ShadowValidationEngine()
        signal = {"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 150.0}
        mismatched_intent = {"symbol": "AAPL", "side": "SELL", "quantity": 10, "price": 150.0}
        is_parity, discrepancies = engine.evaluate_order_intent_parity(signal, mismatched_intent)
        assert is_parity is False
        assert len(discrepancies) > 0

    def test_6d_p6_queue_position_and_fill_modeling(self):
        """Verify 6D-P6 simulated order fill & L2 queue position modeling."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p6_queue_position_and_fill_modeling()
        assert res["status"] == "PASS"

    def test_6d_p7_realtime_slippage_measurement(self):
        """Verify 6D-P7 real-time trigger vs fill price slippage measurement."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p7_realtime_slippage_measurement()
        assert res["status"] == "PASS"
        assert res["slippage_pct"] == 0.05

    def test_6d_p8_end_to_end_latency_tracking(self):
        """Verify 6D-P8 end-to-end latency tracking (<150ms target)."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p8_end_to_end_latency_tracking()
        assert res["status"] == "PASS"
        assert res["latency_ms"] < 150.0

    def test_6d_p9_passive_broker_response_observation(self):
        """Verify 6D-P9 passive broker ACK / reject payload observation."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p9_passive_broker_response_observation()
        assert res["status"] == "PASS"

    def test_6d_p10_market_data_staleness_guard(self):
        """Verify 6D-P10 market data staleness (>2s) fail-closed SafetyState.HOLD guard."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p10_market_data_staleness_guard()
        assert res["status"] == "PASS"
        assert res["safety_state_after_gap"] == "HOLD"

    def test_6d_p11_signal_drift_guard(self):
        """Verify 6D-P11 signal drift (>0.1%) fail-closed SafetyState.HOLD guard."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p11_signal_drift_guard()
        assert res["status"] == "PASS"
        assert res["safety_state_after_drift"] == "HOLD"

    def test_6d_p12_execution_drift_tracking(self):
        """Verify 6D-P12 execution drift & fill variance tracking."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p12_execution_drift_tracking()
        assert res["status"] == "PASS"

    def test_6d_p13_shadow_vs_paper_reconciliation(self):
        """Verify 6D-P13 automated shadow-vs-paper ledger reconciliation."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p13_shadow_vs_paper_reconciliation()
        assert res["status"] == "PASS"
        assert res["status_match"] is True

    def test_6d_p14_feed_disconnect_recovery(self):
        """Verify 6D-P14 feed disconnect recovery & state reconstruction without intent duplication."""
        certifier = ShadowExecutionCertifier()
        res = certifier.verify_6d_p14_feed_disconnect_recovery()
        assert res["status"] == "PASS"
        assert res["no_duplicate_intents"] is True

    def test_6d_p15_shadow_manifest_generation(self):
        """Verify 6D-P15 complete shadow production certification manifest generation."""
        certifier = ShadowExecutionCertifier()
        all_passed, manifest = certifier.execute_full_6d_shadow_audit()
        assert all_passed is True
        assert manifest["invariants_total"] == 15
        assert manifest["invariants_passed"] == 15
        assert manifest["signing_status"] == "CERTIFICATION_SIGNING_PENDING"
        assert len(manifest["manifest_sha256"]) == 64
        assert manifest["capital_exposure"] == "$0.00 (ZERO-CAPITAL)"
