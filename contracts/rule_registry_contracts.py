# contracts/rule_registry_contracts.py
"""
Canonical Broker & Exchange Rule Registry Contracts for NexTrade (Sub-Phase 4N).
Defines versioned, auditable domain models for broker capability specifications, exchange trading rules,
margin parameters, and square-off cutoffs (Invariants 4N-P1, 4N-P4).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType


@dataclass(frozen=True)
class ExchangeRuleRecord:
    """
    Versioned exchange rule specification (trading hours, square-off cutoffs, lot sizes).
    """
    exchange: str  # NSE, BSE, MCX, NCDEX, US_EXCHANGES
    segment: MarketSegment
    trading_hours_start: str  # e.g., "09:15"
    trading_hours_end: str    # e.g., "15:30"
    square_off_cutoff: str    # e.g., "15:15"
    lot_size: int = 1
    version: str = "v1.0"
    last_verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerCapabilityRecord:
    """
    Versioned capability record for an active broker adapter (Invariant 4N-P4).
    """
    adapter_id: str  # IBKR, ANGEL_ONE, PAPER
    supported_segments: List[MarketSegment]
    supported_products: List[ProductType]
    supported_order_types: List[OrderType]
    max_leverage_multiplier: float = 1.0
    version: str = "v1.0"


class RuleRegistryStore:
    """
    Thread-safe, versioned repository of broker and exchange rule specifications.
    """

    def __init__(self):
        self._exchange_rules: Dict[Tuple[str, MarketSegment], ExchangeRuleRecord] = {
            ("NSE", MarketSegment.EQUITY): ExchangeRuleRecord(
                exchange="NSE",
                segment=MarketSegment.EQUITY,
                trading_hours_start="09:15",
                trading_hours_end="15:30",
                square_off_cutoff="15:15",
                lot_size=1
            ),
            ("NSE", MarketSegment.DERIVATIVES_FO): ExchangeRuleRecord(
                exchange="NSE",
                segment=MarketSegment.DERIVATIVES_FO,
                trading_hours_start="09:15",
                trading_hours_end="15:30",
                square_off_cutoff="15:15",
                lot_size=50
            ),
            ("US_EXCHANGES", MarketSegment.EQUITY): ExchangeRuleRecord(
                exchange="US_EXCHANGES",
                segment=MarketSegment.EQUITY,
                trading_hours_start="09:30",
                trading_hours_end="16:00",
                square_off_cutoff="15:45",
                lot_size=1
            )
        }

        self._broker_capabilities: Dict[str, BrokerCapabilityRecord] = {
            "IBKR": BrokerCapabilityRecord(
                adapter_id="IBKR",
                supported_segments=[MarketSegment.EQUITY, MarketSegment.DERIVATIVES_FO],
                supported_products=[ProductType.CNC_DELIVERY, ProductType.MIS_INTRADAY],
                supported_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.SL_MARKET, OrderType.GTT]
            ),
            "PAPER": BrokerCapabilityRecord(
                adapter_id="PAPER",
                supported_segments=[MarketSegment.EQUITY, MarketSegment.DERIVATIVES_FO, MarketSegment.COMMODITIES],
                supported_products=[ProductType.CNC_DELIVERY, ProductType.MIS_INTRADAY, ProductType.MTF_MARGIN],
                supported_order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.SL_MARKET, OrderType.GTT]
            )
        }

    def get_exchange_rule(self, exchange: str, segment: MarketSegment) -> Optional[ExchangeRuleRecord]:
        return self._exchange_rules.get((exchange, segment))

    def get_broker_capability(self, adapter_id: str) -> Optional[BrokerCapabilityRecord]:
        return self._broker_capabilities.get(adapter_id)
