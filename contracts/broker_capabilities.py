# contracts/broker_capabilities.py
"""
Broker Capability Discovery & Central Validation Layer for NexTrade (Sub-Phase 4B).
Provides an immutable declaration of features supported by a specific broker adapter,
and a central CapabilityValidator enforcing Layer 1 capability validation.
"""
from dataclasses import dataclass, field
from typing import Set

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderType


@dataclass(frozen=True)
class BrokerCapabilities:
    """Immutable capability matrix for a concrete broker adapter implementation."""
    broker_name: str
    supports_market_orders: bool = True
    supports_limit_orders: bool = True
    supports_stop_orders: bool = True
    supports_stop_limit_orders: bool = True
    supports_bracket_orders: bool = False
    supports_trailing_stops: bool = False
    supports_order_modification: bool = True
    supports_partial_fills: bool = True
    supports_fractional_shares: bool = False
    supports_short_selling: bool = False
    supports_websocket_events: bool = False
    max_orders_per_second: int = 10

    def supported_order_types(self) -> Set[BrokerOrderType]:
        """Returns set of supported BrokerOrderType enums."""
        types = set()
        if self.supports_market_orders:
            types.add(BrokerOrderType.MARKET)
        if self.supports_limit_orders:
            types.add(BrokerOrderType.LIMIT)
        if self.supports_stop_orders:
            types.add(BrokerOrderType.STOP)
        if self.supports_stop_limit_orders:
            types.add(BrokerOrderType.STOP_LIMIT)
        if self.supports_trailing_stops:
            types.add(BrokerOrderType.TRAILING_STOP)
        return types


class CapabilityValidator:
    """Central Layer 1 Capability Validator enforcing broker-neutral order feasibility."""

    @staticmethod
    def validate(capabilities: BrokerCapabilities, request: BrokerOrderRequest) -> None:
        """
        Validates that a BrokerOrderRequest satisfies the BrokerCapabilities matrix.
        Raises ValueError if unsupported features or parameters are requested.
        """
        if not isinstance(capabilities, BrokerCapabilities):
            raise ValueError(f"Expected BrokerCapabilities instance, got {type(capabilities).__name__}")
        if not isinstance(request, BrokerOrderRequest):
            raise ValueError(f"Expected BrokerOrderRequest instance, got {type(request).__name__}")

        # Check Order Type Support
        supported_types = capabilities.supported_order_types()
        if request.order_type not in supported_types:
            raise ValueError(
                f"Broker '{capabilities.broker_name}' does not support order type '{request.order_type.value}'"
            )

        # Check Fractional Shares Support
        if not capabilities.supports_fractional_shares and not request.quantity.is_integer():
            raise ValueError(
                f"Broker '{capabilities.broker_name}' does not support fractional share quantity ({request.quantity})"
            )

        # Check Trailing Stop Support
        if request.order_type == BrokerOrderType.TRAILING_STOP and not capabilities.supports_trailing_stops:
            raise ValueError(f"Broker '{capabilities.broker_name}' does not support trailing stop orders")
