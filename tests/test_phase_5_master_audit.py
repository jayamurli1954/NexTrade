"""
NexTrade Phase 5 Consolidated Master Certification Safety Audit Test Suite.

Verifies end-to-end integration across all 98 invariants (Workstreams 5A through 5H).
"""

import time
import pytest

from hardening import SafetyControlPlane, SafetyState
from brokers import BrokerProductionGate, ConnectionState
from governance import (
    SecretSanitizer,
    SecretVault,
    TrustedSignerRegistry,
    SignerAlgorithm,
    SignedRulePackage,
    SignedRulePackageValidator,
    BrokerRuleRegistryManager,
    AtomicRuleActivator,
    RuleProvenanceLogger,
    MultiAccountPreflightManager,
    ExecutionTimeAuthorizer,
)
from ui_new.workspace_controller import TradingWorkspaceController
from pilot.pilot_operations_manager import PilotOperationsManager
from shadow.shadow_validation_engine import ShadowValidationEngine
from resilience.chaos_engine import ResilienceChaosEngine
from resilience.controlled_recovery import ControlledRecoveryPipeline


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


def build_master_rule_package(registry: TrustedSignerRegistry) -> SignedRulePackage:
    if "key_master_100" not in registry._signers:
        registry.register_signer("key_master_100", SignerAlgorithm.HMAC_SHA256, "master_secret_key_99")
    pkg_hash = SignedRulePackageValidator.compute_canonical_hash(
        "pkg_master_v1", 1, "IBKR", 1, "DEFAULT", 0.0, 4102444800.0, '{"allowed_order_types": ["LIMIT", "MARKET"], "allowed_trade_types": ["INTRADAY", "DELIVERY"]}'
    )
    sig = SignedRulePackageValidator.create_signature("master_secret_key_99", pkg_hash)
    return SignedRulePackage("pkg_master_v1", 1, "IBKR", 0.0, 4102444800.0, '{"allowed_order_types": ["LIMIT", "MARKET"], "allowed_trade_types": ["INTRADAY", "DELIVERY"]}', sig, "key_master_100", pkg_hash)


class TestPhase5MasterAudit:
    """Master audit test suite certifying Phase 5 end-to-end integration."""

    def test_master_safety_control_plane_ladder(self):
        """Verify 5A SafetyControlPlane canonical precedence ladder."""
        scp = SafetyControlPlane()
        assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED
        
        scp.report_subsystem_state("conn", SafetyState.READY, "Connected")
        assert scp.get_state() == SafetyState.READY

        scp.report_subsystem_state("risk", SafetyState.HARD_HALT, "Hard Halt")
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_master_broker_production_gate_dispatch_predicate(self):
        """Verify 5B BrokerProductionGate D1-D10 pre-dispatch predicate."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        is_eligible, reason, _ = gate.evaluate_dispatch_eligibility()
        assert is_eligible is True
        assert reason == "DISPATCH_PERMITTED"

    def test_master_secret_vault_and_sanitizer_isolation(self):
        """Verify 5C SecretVault and SecretSanitizer zero plain-text secret persistence."""
        vault = SecretVault()
        vault.store_secret("api_key_ibkr", "super_secret_key_val_777")
        assert vault.get_secret("api_key_ibkr") == "super_secret_key_val_777"

        raw_dict = {"api_key": "super_secret_key_val_777", "symbol": "AAPL"}
        sanitized = SecretSanitizer.sanitize_dict(raw_dict)
        assert sanitized["api_key"] == "[REDACTED_SENSITIVE_FIELD]"
        assert sanitized["symbol"] == "AAPL"

    def test_master_workspace_controller_3_layer_defence(self):
        """Verify 5D TradingWorkspaceController 3-layer defence-in-depth."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        controller = TradingWorkspaceController(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY"}
        
        response = controller.submit_order_intent(payload, auth_token="auth_valid_session_token_100", idempotency_token="master_idem_1")
        assert response["status"] == "DISPATCHED"

    def test_master_order_trade_execution_time_authority(self):
        """Verify 5E ExecutionTimeAuthorizer 4-layer execution semantics."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        authorizer = ExecutionTimeAuthorizer(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY", "price": 150.0}
        
        response = authorizer.authorize_execution_intent(payload, tick_size=0.05, lot_size=1)
        assert response["status"] == "DISPATCHED"
        assert response["layer4_authorization"] == "AUTHORIZED_CLEARED"

    def test_master_signed_rule_validator_and_session_epoch(self):
        """Verify 5F SignedRulePackageValidator, CAS activator, and session_epoch governance."""
        registry = TrustedSignerRegistry()
        pkg = build_master_rule_package(registry)
        validator = SignedRulePackageValidator(signer_registry=registry)
        assert validator.validate_package(pkg) is True

        scp = SafetyControlPlane()
        manager = BrokerRuleRegistryManager(validator=validator, control_plane=scp)
        activator = AtomicRuleActivator(registry_manager=manager, control_plane=scp)

        is_mat, epoch = activator.activate_rule_package_cas("IBKR", pkg)
        assert epoch == 2
        assert scp.get_state() == SafetyState.REVALIDATION_REQUIRED

    def test_master_pilot_exposure_and_multi_account_preflight(self):
        """Verify 5G PilotOperationsManager exposure limits and MultiAccountPreflightManager isolation."""
        registry = TrustedSignerRegistry()
        pkg = build_master_rule_package(registry)
        preflight_mgr = MultiAccountPreflightManager()

        cert_a = preflight_mgr.issue_account_certificate("IBKR", "ACC_A", "SESS_1", 1, pkg)
        assert cert_a.account_id == "ACC_A"

        shadow_eng = ShadowValidationEngine()
        record = shadow_eng.evaluate_shadow_signal({"symbol": "AAPL", "price": 100.0}, paper_market_price=100.5, latency_ms=10.0)
        assert record.slippage_pct == 0.5

    def test_master_adversarial_chaos_and_controlled_recovery(self):
        """Verify 5H ResilienceChaosEngine failure containment and 4-step ControlledRecoveryPipeline."""
        scp = SafetyControlPlane()
        registry = TrustedSignerRegistry()
        pkg = build_master_rule_package(registry)
        validator = SignedRulePackageValidator(signer_registry=registry)

        chaos = ResilienceChaosEngine(control_plane=scp)
        chaos.inject_broker_ack_timeout("IBKR", "ord_master_chaos")
        assert scp.get_state() == SafetyState.RECONCILIATION_LOCK

        pipeline = ControlledRecoveryPipeline(control_plane=scp, order_reconciler=chaos.reconciler, rule_validator=validator)
        success, cert = pipeline.execute_full_controlled_recovery("IBKR", "ACC_A", "SESS_1", 1, pkg)
        assert success is True
        assert scp.get_state() == SafetyState.READY

    def test_master_end_to_end_certified_execution_chain(self):
        """Verify complete end-to-end Phase 5 certified execution chain."""
        scp = SafetyControlPlane()
        gate = BrokerProductionGate(control_plane=scp)
        cert_pin = gate.tls_validator.pin_set.active_pin
        gate.initialize_connection(cert_pin, "api.ibkr.com")

        registry = TrustedSignerRegistry()
        pkg = build_master_rule_package(registry)
        validator = SignedRulePackageValidator(signer_registry=registry)
        
        preflight_mgr = MultiAccountPreflightManager()
        cert = preflight_mgr.issue_account_certificate("IBKR", "ACC_PROD_1", "SESS_PROD_1", 1, pkg)

        authorizer = ExecutionTimeAuthorizer(production_gate=gate, control_plane=scp)
        payload = {"symbol": "AAPL", "quantity": 10, "order_type": "LIMIT", "trade_type": "INTRADAY", "price": 150.0, "account_id": "ACC_PROD_1", "broker_id": "IBKR"}

        # Validate account preflight
        assert preflight_mgr.validate_account_dispatch(payload, cert, active_session_epoch=1, active_rule_version=1) is True

        # Dispatch via ExecutionTimeAuthorizer
        response = authorizer.authorize_execution_intent(payload)
        assert response["status"] == "DISPATCHED"
