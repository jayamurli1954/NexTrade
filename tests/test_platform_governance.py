# tests/test_platform_governance.py
"""
Platform Governance Test Suite for NexTrade (Sub-Phase 4N).
Verifies:
1. RuleRegistryStore versioned broker capability and exchange rule retrieval (Invariant 4N-P1).
2. CapabilityResolver 5-way dynamic tradability intersection (Invariants 4N-P4, 4N-P8).
3. ProductionActivationManager explicit human production authorization (Invariant 4N-P2).
4. SecretSanitizer cryptographic key and secret masking (Invariant 4N-P3).
5. TradeTemplateEngine trade type templates (Invariant 4N-P5).
6. PlatformGovernanceAuditor certificate consolidation (Invariant 4N-P6).
"""
import pytest
from datetime import datetime, timezone

from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType
from contracts.rule_registry_contracts import RuleRegistryStore
from governance.capability_resolver import CapabilityResolver
from governance.activation_manager import ProductionActivationManager
from governance.secret_sanitizer import SecretSanitizer
from governance.trade_templates import TradeTemplateEngine
from ui_new.governance_panel import GovernancePanel
from audit.platform_governance_auditor import PlatformGovernanceAuditor


def test_rule_registry_store_retrieval():
    """Verify RuleRegistryStore retrieves versioned rules and broker capabilities."""
    store = RuleRegistryStore()
    rule = store.get_exchange_rule("NSE", MarketSegment.EQUITY)
    assert rule is not None
    assert rule.square_off_cutoff == "15:15"

    broker = store.get_broker_capability("IBKR")
    assert broker is not None
    assert ProductType.CNC_DELIVERY in broker.supported_products


def test_capability_resolver_5_way_intersection():
    """Verify CapabilityResolver evaluates tradability across 5-way dynamic intersection (Invariants 4N-P4, 4N-P8)."""
    resolver = CapabilityResolver()

    # 1. IBKR + Equity + CNC + Limit -> TRADABLE
    ok1, msg1, lot1 = resolver.resolve_tradability("IBKR", "NSE", MarketSegment.EQUITY, ProductType.CNC_DELIVERY, OrderType.LIMIT)
    assert ok1 is True
    assert "RESOLVER_APPROVED" in msg1
    assert lot1 == 1

    # 2. IBKR + Commodities -> REJECTED (IBKR capability store does not support commodities)
    ok2, msg2, _ = resolver.resolve_tradability("IBKR", "NSE", MarketSegment.COMMODITIES, ProductType.MIS_INTRADAY, OrderType.MARKET)
    assert ok2 is False
    assert "CAPABILITY_REJECTED" in msg2


def test_production_activation_human_authorization():
    """Verify ProductionActivationManager requires explicit human operator signature (Invariant 4N-P2)."""
    mgr = ProductionActivationManager()
    assert mgr.is_production_active is False

    # Without operator signature -> DENIED
    ok_fail, msg_fail = mgr.authorize_production_activation("", "", "CERT-READINESS-01")
    assert ok_fail is False
    assert "operator_id and human_authorization_id are required" in msg_fail

    # With operator signature -> APPROVED
    ok_pass, msg_pass = mgr.authorize_production_activation("OP-PROD-01", "AUTH-HUMAN-999", "CERT-READINESS-01")
    assert ok_pass is True
    assert mgr.is_production_active is True


def test_secret_sanitizer_masking():
    """Verify SecretSanitizer strips secret HMAC keys and tokens (Invariant 4N-P3)."""
    raw_text = "Connecting with hmac_signature: 8c2a4be45280ac61e9c377d9c5f3de98d2929342b3dc15b877b2c7ab2046c150 and token_id: TOK1234567890ABCDEF"
    clean_text = SecretSanitizer.sanitize_text(raw_text)

    assert "8c2a4be4" not in clean_text
    assert "[REDACTED_HMAC_KEY]" in clean_text
    assert "[REDACTED_TOKEN]" in clean_text


def test_trade_template_engine():
    """Verify TradeTemplateEngine provides pre-configured safe templates (Invariant 4N-P5)."""
    engine = TradeTemplateEngine()
    templates = engine.list_templates()
    assert len(templates) >= 5

    t_delivery = engine.get_template("EQUITY_DELIVERY")
    assert t_delivery is not None
    assert t_delivery.product == ProductType.CNC_DELIVERY


def test_platform_governance_auditor():
    """Verify PlatformGovernanceAuditor consolidates 4A–4N evidence stack (Invariant 4N-P6)."""
    auditor = PlatformGovernanceAuditor()
    cert = auditor.audit_platform_governance()

    assert cert.status == "READY"
    assert len(cert.phase_stack) == 14
    assert cert.rule_registry_active is True
    assert cert.secret_sanitizer_active is True
    assert len(cert.evidence_hash) == 64
