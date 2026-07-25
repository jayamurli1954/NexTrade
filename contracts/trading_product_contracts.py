# contracts/trading_product_contracts.py
"""
Canonical Trading Capability & Product Domain Contracts for NexTrade (Sub-Phase 4M).
Defines strongly typed, frozen models for Market Segments, Trading Products (CNC, MIS, MTF),
Advanced Order Types (Market, Limit, SL, SL-M, IOC, AMO, GTT), and Broker Capability Matrices (Invariants 4M-P2, 4M-P9).
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple


class MarketSegment(str, Enum):
    EQUITY = "EQUITY"
    DERIVATIVES_FO = "DERIVATIVES_FO"
    COMMODITIES = "COMMODITIES"
    CURRENCY = "CURRENCY"


class ProductType(str, Enum):
    CNC_DELIVERY = "CNC_DELIVERY"
    MIS_INTRADAY = "MIS_INTRADAY"
    MTF_MARGIN = "MTF_MARGIN"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    SL_MARKET = "SL_MARKET"
    IOC = "IOC"
    AMO = "AMO"
    GTT = "GTT"


@dataclass(frozen=True)
class ProductCapabilityRecord:
    """
    Immutable specification of allowed order types for a segment and product combination.
    """
    segment: MarketSegment
    product: ProductType
    allowed_order_types: List[OrderType]
    is_enabled: bool = True
    broker_supported: bool = True


class TradingProductMatrix:
    """
    Authoritative Capability Matrix enforcing valid segment, product, and order type combinations (Invariant 4M-P2, 4M-P9).
    """

    def __init__(self):
        self._capabilities: Dict[Tuple[MarketSegment, ProductType], ProductCapabilityRecord] = {
            (MarketSegment.EQUITY, ProductType.CNC_DELIVERY): ProductCapabilityRecord(
                segment=MarketSegment.EQUITY,
                product=ProductType.CNC_DELIVERY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.GTT],
                is_enabled=True,
                broker_supported=True
            ),
            (MarketSegment.EQUITY, ProductType.MIS_INTRADAY): ProductCapabilityRecord(
                segment=MarketSegment.EQUITY,
                product=ProductType.MIS_INTRADAY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.SL_MARKET, OrderType.IOC],
                is_enabled=True,
                broker_supported=True
            ),
            (MarketSegment.DERIVATIVES_FO, ProductType.MIS_INTRADAY): ProductCapabilityRecord(
                segment=MarketSegment.DERIVATIVES_FO,
                product=ProductType.MIS_INTRADAY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.SL_MARKET],
                is_enabled=True,
                broker_supported=True
            ),
            (MarketSegment.COMMODITIES, ProductType.MIS_INTRADAY): ProductCapabilityRecord(
                segment=MarketSegment.COMMODITIES,
                product=ProductType.MIS_INTRADAY,
                allowed_order_types=[OrderType.MARKET, OrderType.LIMIT],
                is_enabled=False,  # Phase 5 roadmap
                broker_supported=False
            )
        }

    def validate_capability(
        self,
        segment: MarketSegment,
        product: ProductType,
        order_type: OrderType
    ) -> Tuple[bool, str]:
        """
        Validates if segment + product + order_type combination is enabled and supported (Invariant 4M-P2, 4M-P9).
        """
        key = (segment, product)
        if key not in self._capabilities:
            return False, f"CAPABILITY_REJECTED: Combination ({segment.value}, {product.value}) is not enabled on NexTrade"

        record = self._capabilities[key]
        if not record.is_enabled:
            return False, f"CAPABILITY_REJECTED: Product '{product.value}' under segment '{segment.value}' is currently disabled on product roadmap"

        if not record.broker_supported:
            return False, f"CAPABILITY_REJECTED: Product '{product.value}' is not supported by active broker adapter"

        if order_type not in record.allowed_order_types:
            allowed_names = [ot.value for ot in record.allowed_order_types]
            return False, f"CAPABILITY_REJECTED: Order type '{order_type.value}' is not permitted for ({segment.value}, {product.value}). Allowed: {allowed_names}"

        return True, f"CAPABILITY_APPROVED: Order combination ({segment.value}, {product.value}, {order_type.value}) is valid"
