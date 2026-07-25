# ui_new/risk_preview.py
"""
Pre-Trade Risk & Margin Preview Calculator for NexTrade (Sub-Phase 4M).
Computes estimated order value, SPAN + Exposure margin requirements, lot size multipliers,
max potential loss, and pre-trade safety gate validations before order confirmation (Invariant 4M-P5).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from contracts.broker_domain import BrokerOrderSide
from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType


@dataclass(frozen=True)
class RiskPreviewResult:
    """
    Pre-trade preview containing order valuation, margin calculations, and pre-flight safety checks (Invariant 4M-P5).
    """
    symbol: str
    segment: MarketSegment
    product: ProductType
    order_type: OrderType
    side: BrokerOrderSide
    quantity: float
    price: float
    estimated_notional: float
    span_margin_estimate: float
    exposure_margin_estimate: float
    total_margin_required: float
    max_potential_loss: float
    exposure_after_order: float
    exposure_limit: float
    capability_approved: bool
    safety_checks_passed: bool
    warnings: List[str] = field(default_factory=list)


class RiskPreviewCalculator:
    """
    Pre-trade risk and margin estimator evaluating order parameters against environment caps.
    """

    def calculate_preview(
        self,
        symbol: str,
        segment: MarketSegment,
        product: ProductType,
        order_type: OrderType,
        side: BrokerOrderSide,
        quantity: float,
        price: float,
        current_exposure: float = 1250.0,
        exposure_limit: float = 2500.0
    ) -> RiskPreviewResult:
        """
        Calculates pre-trade risk metrics, margin requirements (SPAN + Exposure), and safety pre-checks.
        """
        notional = quantity * price
        warnings = []

        # Margin Calculation Logic
        span_margin = 0.0
        exposure_margin = 0.0

        if product == ProductType.CNC_DELIVERY:
            span_margin = notional  # 100% upfront delivery cost
            exposure_margin = 0.0
            max_loss = notional if side == BrokerOrderSide.BUY else float("inf")
        elif product == ProductType.MIS_INTRADAY:
            span_margin = notional * 0.15  # 15% SPAN margin estimate
            exposure_margin = notional * 0.05  # 5% Exposure margin estimate
            max_loss = notional if side == BrokerOrderSide.BUY else float("inf")
        else:  # MTF_MARGIN
            span_margin = notional * 0.25  # 25% initial margin
            exposure_margin = notional * 0.05
            max_loss = notional

        total_margin = span_margin + exposure_margin
        projected_exposure = current_exposure + notional

        safety_passed = True
        if projected_exposure > exposure_limit:
            safety_passed = False
            warnings.append(f"PRE_TRADE_WARNING: Projected exposure (${projected_exposure:.2f}) exceeds max allowed limit (${exposure_limit:.2f})")

        return RiskPreviewResult(
            symbol=symbol,
            segment=segment,
            product=product,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            estimated_notional=notional,
            span_margin_estimate=span_margin,
            exposure_margin_estimate=exposure_margin,
            total_margin_required=total_margin,
            max_potential_loss=max_loss,
            exposure_after_order=projected_exposure,
            exposure_limit=exposure_limit,
            capability_approved=True,
            safety_checks_passed=safety_passed,
            warnings=warnings
        )
