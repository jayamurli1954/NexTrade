# governance/trade_templates.py
"""
Trade Type Template Engine for NexTrade (Sub-Phase 4N).
Provides pre-configured, safe templates for Equity Delivery (CNC), Intraday (MIS), MTF Margin,
Futures, Options Buying, and Options Writing without bypassing backend safety gates (Invariant 4N-P5).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType


@dataclass(frozen=True)
class TradeTemplate:
    """
    Pre-configured trade type template specification.
    """
    template_id: str
    name: str
    segment: MarketSegment
    product: ProductType
    allowed_order_types: List[OrderType]
    typical_horizon: str
    margin_description: str
    risk_level: str
    is_enabled: bool = True


class TradeTemplateEngine:
    """
    Repository of standard trade templates for Smart Trade Ticket pre-configuration.
    """

    def __init__(self):
        self._templates: Dict[str, TradeTemplate] = {
            "EQUITY_DELIVERY": TradeTemplate(
                template_id="EQUITY_DELIVERY",
                name="Equity Delivery (CNC)",
                segment=MarketSegment.EQUITY,
                product=ProductType.CNC_DELIVERY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.GTT],
                typical_horizon="Long-term holding",
                margin_description="100% upfront cash payment required",
                risk_level="Low to Moderate"
            ),
            "EQUITY_INTRADAY": TradeTemplate(
                template_id="EQUITY_INTRADAY",
                name="Equity Intraday (MIS)",
                segment=MarketSegment.EQUITY,
                product=ProductType.MIS_INTRADAY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.SL_MARKET],
                typical_horizon="Same-day session (Auto square-off)",
                margin_description="~15% SPAN + 5% Exposure margin",
                risk_level="High"
            ),
            "EQUITY_MTF": TradeTemplate(
                template_id="EQUITY_MTF",
                name="Margin Trading Facility (MTF)",
                segment=MarketSegment.EQUITY,
                product=ProductType.MTF_MARGIN,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT],
                typical_horizon="Leveraged delivery holding",
                margin_description="~25% upfront margin + interest",
                risk_level="Moderate to High"
            ),
            "FUTURES_INTRADAY": TradeTemplate(
                template_id="FUTURES_INTRADAY",
                name="Futures Intraday (F&O)",
                segment=MarketSegment.DERIVATIVES_FO,
                product=ProductType.MIS_INTRADAY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS],
                typical_horizon="Contract expiry / Intraday",
                margin_description="10% - 25% Contract SPAN + Exposure margin",
                risk_level="Very High"
            ),
            "OPTIONS_BUYING": TradeTemplate(
                template_id="OPTIONS_BUYING",
                name="Options Buying (Call / Put)",
                segment=MarketSegment.DERIVATIVES_FO,
                product=ProductType.MIS_INTRADAY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT],
                typical_horizon="Contract expiry / Premium trading",
                margin_description="100% upfront premium cost only",
                risk_level="High (Max loss = Premium paid)"
            )
        }

    def get_template(self, template_id: str) -> Optional[TradeTemplate]:
        return self._templates.get(template_id)

    def list_templates(self) -> List[TradeTemplate]:
        return list(self._templates.values())
