# ui_new/trade_ticket.py
"""
Interactive Smart Trade Ticket & Order Entry Widget for NexTrade (Sub-Phase 4M).
Provides segment selection, dynamic product filtering, order type variations, and pre-trade safety review modals (Invariant 4M-P1, 4M-P5).
"""
from typing import Dict, Any, Tuple, Optional

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType
from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType, TradingProductMatrix
from ui_new.risk_preview import RiskPreviewCalculator, RiskPreviewResult
from ui_new.safety_explainer import SafetyExplainer, SafetyExplanation


class TradeTicket:
    """
    Smart trade ticket manager providing user-facing order validation and pre-trade risk previews.
    """

    def __init__(self):
        self.matrix = TradingProductMatrix()
        self.risk_calculator = RiskPreviewCalculator()
        self.explainer = SafetyExplainer()

    def prepare_trade_ticket(
        self,
        symbol: str,
        segment: MarketSegment,
        product: ProductType,
        order_type: OrderType,
        side: BrokerOrderSide,
        quantity: float,
        price: float
    ) -> Tuple[bool, Optional[RiskPreviewResult], Optional[SafetyExplanation], str]:
        """
        Validates capability matrix and calculates pre-trade risk preview.
        Returns (valid: bool, preview: Optional[RiskPreviewResult], explanation: Optional[SafetyExplanation], message: str).
        """
        # 1. Validate Trading Product Capability Matrix (Invariant 4M-P2, 4M-P9)
        cap_valid, cap_msg = self.matrix.validate_capability(segment, product, order_type)
        if not cap_valid:
            exp = self.explainer.explain_denial(cap_msg)
            return False, None, exp, cap_msg

        # 2. Calculate Pre-Trade Risk & Margin Preview (Invariant 4M-P5)
        preview = self.risk_calculator.calculate_preview(
            symbol=symbol,
            segment=segment,
            product=product,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price
        )

        if not preview.safety_checks_passed:
            exp = self.explainer.explain_denial(preview.warnings[0] if preview.warnings else "EXPOSURE_EXCEEDED")
            return False, preview, exp, "PRE_TRADE_BLOCKED: Order violates pre-trade risk bounds"

        exp = SafetyExplanation(
            decision="READY",
            primary_reason="Order Passed All Pre-Trade Safety Checks",
            explanation_text="Order capability is valid and estimated exposure is within active bounds.",
            required_action="Confirm order submission.",
            active_barriers=[]
        )

        return True, preview, exp, "TICKET_PREPARED: Order ready for user confirmation"
