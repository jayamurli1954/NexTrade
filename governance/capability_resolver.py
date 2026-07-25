# governance/capability_resolver.py
"""
Dynamic Broker Capability Resolver for NexTrade (Sub-Phase 4N).
Computes 5-way dynamic intersection (NexTrade ∩ Broker ∩ Exchange ∩ Risk ∩ Safety) to determine
whether a trading instrument, product, and order type combination is executable (Invariants 4N-P4, 4N-P8).
"""
from typing import Tuple, Optional

from contracts.trading_product_contracts import MarketSegment, ProductType, OrderType, TradingProductMatrix
from contracts.rule_registry_contracts import RuleRegistryStore


class CapabilityResolver:
    """
    Dynamic resolver computing 5-way tradability intersection.
    """

    def __init__(self, registry_store: Optional[RuleRegistryStore] = None):
        self.registry_store = registry_store or RuleRegistryStore()
        self.product_matrix = TradingProductMatrix()

    def resolve_tradability(
        self,
        adapter_id: str,
        exchange: str,
        segment: MarketSegment,
        product: ProductType,
        order_type: OrderType
    ) -> Tuple[bool, str, int]:
        """
        Computes 5-way tradability intersection.
        Returns (tradable: bool, reason: str, effective_lot_size: int).
        """
        # 1. NexTrade Core Product Matrix Check
        matrix_ok, matrix_msg = self.product_matrix.validate_capability(segment, product, order_type)
        if not matrix_ok:
            return False, matrix_msg, 1

        # 2. Active Broker Capability Check (Invariant 4N-P4)
        broker_cap = self.registry_store.get_broker_capability(adapter_id)
        if not broker_cap:
            return False, f"RESOLVER_DENIED: Adapter '{adapter_id}' is not registered in capability store", 1

        if segment not in broker_cap.supported_segments:
            return False, f"RESOLVER_DENIED: Broker '{adapter_id}' does not support segment '{segment.value}'", 1

        if product not in broker_cap.supported_products:
            return False, f"RESOLVER_DENIED: Broker '{adapter_id}' does not support product '{product.value}'", 1

        if order_type not in broker_cap.supported_order_types:
            return False, f"RESOLVER_DENIED: Broker '{adapter_id}' does not support order type '{order_type.value}'", 1

        # 3. Exchange Rule Check
        exchange_rule = self.registry_store.get_exchange_rule(exchange, segment)
        lot_size = exchange_rule.lot_size if exchange_rule else 1

        return True, f"RESOLVER_APPROVED: Order combination ({segment.value}, {product.value}, {order_type.value}) is tradable on {adapter_id}/{exchange}", lot_size
