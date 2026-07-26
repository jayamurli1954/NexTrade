"""
NexTrade Phase 6C — Broker Production Connectivity Audit Test Suite.

Verifies all 15 broker production connectivity invariants (6C-P1 through 6C-P15).
"""

import os
import pytest
from hardening import SafetyControlPlane, SafetyState
from brokers.broker_connectivity_certifier import BrokerConnectivityCertifier
from brokers.broker_production_gate import BrokerProductionGate
from brokers.ibkr_adapter import IBKRBrokerAdapter
from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType, BrokerOrderStatus


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase6CBrokerConnectivityAudit:
    """Test suite certifying 6C-P1 through 6C-P15 invariants."""

    def test_6c_p1_endpoint_identity(self):
        """Verify 6C-P1 production broker endpoint identity & DNS resolution."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p1_endpoint_identity()
        assert res["status"] == "PASS"
        assert res["invariant_id"] == "6C-P1"

    def test_6c_p2_tls_chain_validation(self):
        """Verify 6C-P2 TLS certificate chain & CA trust store validation."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p2_tls_chain_validation()
        assert res["status"] == "PASS"
        assert res["ca_trust_store_verified"] is True

    def test_6c_p3_active_pin_verification(self):
        """Verify 6C-P3 active certificate SHA-256 pin match."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p3_active_pin_verification()
        assert res["status"] == "PASS"

    def test_6c_p4_backup_pin_verification(self):
        """Verify 6C-P4 backup certificate pin match & fallback path."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p4_backup_pin_verification()
        assert res["status"] == "PASS"

    def test_6c_p5_pin_rotation_readiness(self):
        """Verify 6C-P5 TLS pin set rotation & failover readiness."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p5_pin_rotation_readiness()
        assert res["status"] == "PASS"

    def test_6c_p6_authenticated_handshake(self):
        """Verify 6C-P6 keyring-authenticated API handshake & secret sanitization."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p6_authenticated_handshake()
        assert res["status"] == "PASS"
        assert res["secret_sanitization_verified"] is True

    def test_6c_p7_account_identity_alignment(self):
        """Verify 6C-P7 broker & account identity alignment."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p7_account_identity_alignment()
        assert res["status"] == "PASS"

    def test_6c_p8_instrument_metadata_integrity(self):
        """Verify 6C-P8 instrument metadata & contract specification integrity."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p8_instrument_metadata_integrity()
        assert res["status"] == "PASS"

    def test_6c_p9_capability_intersection(self):
        """Verify 6C-P9 restrictive capability matrix intersection."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p9_capability_intersection()
        assert res["status"] == "PASS"
        assert res["effective_capabilities"] == ["INTRADAY", "LIMIT"]

    def test_6c_p10_signed_rule_compatibility(self):
        """Verify 6C-P10 signed rule package compatibility & broker matching."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p10_signed_rule_compatibility()
        assert res["status"] == "PASS"

    def test_6c_p11_preflight_session_epoch_binding(self):
        """Verify 6C-P11 account preflight certificate & session epoch binding."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p11_preflight_session_epoch_binding()
        assert res["status"] == "PASS"

    def test_6c_p12_non_capital_sandbox_lifecycle(self):
        """Verify 6C-P12 non-capital sandbox order lifecycle connectivity."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p12_non_capital_sandbox_lifecycle()
        assert res["status"] == "PASS"
        assert "$0.00 (NON-CAPITAL)" in res["capital_exposure"]

        # Also exercise IBKR adapter sandbox lifecycle method
        adapter = IBKRBrokerAdapter()
        req = BrokerOrderRequest(
            nextrade_execution_id="sandbox_req_1",
            idempotency_key="idem_6c_sandbox_1",
            symbol="AAPL",
            side=BrokerOrderSide.BUY,
            order_type=BrokerOrderType.LIMIT,
            quantity=10,
            limit_price=150.0
        )
        res_adapter = adapter.execute_sandbox_non_capital_order(req)
        assert res_adapter.status in (BrokerOrderStatus.SUBMITTED, BrokerOrderStatus.ACKNOWLEDGED, BrokerOrderStatus.FILLED)

    def test_6c_p13_broker_ack_reject_semantics(self):
        """Verify 6C-P13 broker ACK / reject / error semantics parsing."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p13_broker_ack_reject_semantics()
        assert res["status"] == "PASS"

    def test_6c_p14_outage_reconnect_recovery(self):
        """Verify 6C-P14 connection outage, heartbeat & reconnect recovery."""
        certifier = BrokerConnectivityCertifier()
        res = certifier.verify_6c_p14_outage_reconnect_recovery()
        assert res["status"] == "PASS"

    def test_6c_p15_broker_manifest_generation(self):
        """Verify 6C-P15 complete broker connectivity certification manifest generation."""
        certifier = BrokerConnectivityCertifier()
        all_passed, manifest = certifier.execute_full_6c_connectivity_audit()
        assert all_passed is True
        assert manifest["invariants_total"] == 15
        assert manifest["invariants_passed"] == 15
        assert manifest["signing_status"] == "CERTIFICATION_SIGNING_PENDING"
        assert len(manifest["manifest_sha256"]) == 64
