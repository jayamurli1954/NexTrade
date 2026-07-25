# tests/test_user_safety_interface.py
"""
User Safety Interface & Product Matrix Test Suite for NexTrade (Sub-Phase 4M).
Verifies:
1. TradingProductMatrix capability validation and rejection of unsupported combinations (Invariants 4M-P2, 4M-P9).
2. SafetyExplainer technical denial translation into human-readable explanations (Invariants 4M-P3, 4M-P7).
3. SafetyCentre live snapshot generation (Invariants 4M-P4, 4M-P8).
4. RiskPreviewCalculator SPAN + Exposure margin calculations and pre-trade safety checks (Invariant 4M-P5).
5. TradeTicket order validation workflow (Invariant 4M-P1).
6. SafetyPassport 2-level transparency document generation.
"""
import pytest
from datetime import datetime, timezone

from contracts.broker_domain import BrokerOrderSide
from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType, TradingProductMatrix
from ui_new.safety_explainer import SafetyExplainer
from ui_new.safety_centre import SafetyCentre
from ui_new.risk_preview import RiskPreviewCalculator
from ui_new.trade_ticket import TradeTicket
from ui_new.safety_passport import SafetyPassport


def test_trading_product_matrix_validation():
    """Verify TradingProductMatrix approves valid combinations and rejects invalid ones (Invariants 4M-P2, 4M-P9)."""
    matrix = TradingProductMatrix()

    # 1. Equity + CNC + Limit -> APPROVED
    ok1, msg1 = matrix.validate_capability(MarketSegment.EQUITY, ProductType.CNC_DELIVERY, OrderType.LIMIT)
    assert ok1 is True
    assert "CAPABILITY_APPROVED" in msg1

    # 2. Equity + CNC + SL_MARKET -> REJECTED (Not permitted for CNC)
    ok2, msg2 = matrix.validate_capability(MarketSegment.EQUITY, ProductType.CNC_DELIVERY, OrderType.SL_MARKET)
    assert ok2 is False
    assert "not permitted for" in msg2

    # 3. Commodities + MIS + Market -> REJECTED (Disabled on product roadmap)
    ok3, msg3 = matrix.validate_capability(MarketSegment.COMMODITIES, ProductType.MIS_INTRADAY, OrderType.MARKET)
    assert ok3 is False
    assert "currently disabled" in msg3


def test_safety_explainer_denial_translations():
    """Verify SafetyExplainer translates technical denials into actionable explanations (Invariants 4M-P3, 4M-P7)."""
    explainer = SafetyExplainer()

    # Exposure denial
    exp1 = explainer.explain_denial("STAGING_DENIED: Order notional ($5000.00) exceeds max allowed ($1000.00)")
    assert exp1.decision == "REJECT"
    assert exp1.primary_reason == "Exposure Limit Exceeded"
    assert "Reduce order quantity" in exp1.required_action

    # Reconciliation lock denial
    exp2 = explainer.explain_denial("RECONCILIATION_LOCK: Position mismatch detected")
    assert exp2.decision == "HOLD"
    assert exp2.primary_reason == "Position Reconciliation Pending"
    assert "Review broker position statement" in exp2.required_action


def test_safety_centre_live_snapshot():
    """Verify SafetyCentre produces complete SafetyCentreSnapshot (Invariants 4M-P4, 4M-P8)."""
    sc = SafetyCentre()
    snap = sc.get_live_snapshot()

    assert snap.environment == "CONTROLLED_LIVE"
    assert snap.authorization_valid is True
    assert snap.safety_barriers_active_count == 12
    assert snap.position_reconciliation_status == "CLEAN"
    assert snap.resilience_4l_certified is True


def test_risk_preview_calculator_margin():
    """Verify RiskPreviewCalculator calculates SPAN + Exposure margin estimates (Invariant 4M-P5)."""
    rpc = RiskPreviewCalculator()

    preview = rpc.calculate_preview(
        symbol="AAPL",
        segment=MarketSegment.EQUITY,
        product=ProductType.MIS_INTRADAY,
        order_type=OrderType.LIMIT,
        side=BrokerOrderSide.BUY,
        quantity=10.0,
        price=100.0,
        current_exposure=500.0,
        exposure_limit=2500.0
    )

    assert preview.estimated_notional == 1000.0
    assert preview.span_margin_estimate == 150.0  # 15% SPAN
    assert preview.exposure_margin_estimate == 50.0  # 5% Exposure
    assert preview.total_margin_required == 200.0
    assert preview.safety_checks_passed is True


def test_trade_ticket_pre_trade_workflow():
    """Verify TradeTicket enforces matrix capabilities and returns RiskPreviewResult (Invariant 4M-P1)."""
    ticket = TradeTicket()

    # Valid trade ticket
    ok, preview, exp, msg = ticket.prepare_trade_ticket(
        symbol="AAPL",
        segment=MarketSegment.EQUITY,
        product=ProductType.CNC_DELIVERY,
        order_type=OrderType.LIMIT,
        side=BrokerOrderSide.BUY,
        quantity=1.0,
        price=100.0
    )

    assert ok is True
    assert preview is not None
    assert exp.decision == "READY"
    assert "TICKET_PREPARED" in msg


def test_safety_passport_generation():
    """Verify SafetyPassport generates Level 1 user protections and Level 2 4A–4L evidence stack."""
    sp = SafetyPassport()
    doc = sp.generate_passport()

    assert len(doc.level_1_user_protections) == 12
    assert len(doc.level_2_evidence_stack) == 12
    assert "4L Operational Resilience & Incident Certification" in doc.level_2_evidence_stack
    assert "v4.3-phase-4m" in doc.system_version
