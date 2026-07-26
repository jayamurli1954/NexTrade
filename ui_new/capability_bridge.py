"""
NexTrade Phase 5D — Capability Enforcer Bridge.

Binds Phase 4N CapabilityResolver and 4M TradingProductMatrix to ui_new trading workspace view states.
"""

import logging
from typing import Dict, Any, List, Optional, Set

try:
    from governance.capability_resolver import CapabilityResolver
except ImportError:
    CapabilityResolver = None

logger = logging.getLogger("CapabilityEnforcerBridge")


class StaleCapabilityException(Exception):
    """Raised when an operation attempts to consume a stale or revoked capability assertion."""
    pass


class CapabilityEnforcerBridge:
    """
    Bridge connecting backend capability resolver to UI view controls.
    """

    ALLOWED_ORDER_TYPES = {"LIMIT", "MARKET", "SL", "SL-M"}
    ALLOWED_TRADE_TYPES = {"INTRADAY", "DELIVERY", "F&O"}

    def __init__(self, capability_resolver: Optional[Any] = None) -> None:
        self.resolver = capability_resolver or (CapabilityResolver() if CapabilityResolver else None)
        self._cached_capabilities: Dict[str, Dict[str, Any]] = {}

    def get_workspace_capabilities(self, broker_id: str = "IBKR", account_tier: str = "PILOT") -> Dict[str, Any]:
        """
        Resolves allowable order types, trade types, and features for active broker & tier.
        """
        was_stale = self._cached_capabilities.get(broker_id, {}).get("is_stale", False)
        caps = {
            "broker_id": broker_id,
            "account_tier": account_tier,
            "is_trading_allowed": True,
            "allowed_order_types": list(self.ALLOWED_ORDER_TYPES),
            "allowed_trade_types": list(self.ALLOWED_TRADE_TYPES),
            "max_order_value": 100000.0,
            "capability_version": "v1.0-certified",
            "is_stale": was_stale
        }

        if self.resolver and hasattr(self.resolver, "resolve"):
            try:
                resolved = self.resolver.resolve(broker_id, account_tier)
                caps.update(resolved)
            except Exception as e:
                logger.warning("Error resolving capabilities via CapabilityResolver: %s", str(e))

        self._cached_capabilities[broker_id] = caps
        return caps

    def validate_intent_capability(self, order_payload: Dict[str, Any], broker_id: str = "IBKR") -> bool:
        """
        Validates order intent payload against resolved capabilities.
        Raises StaleCapabilityException if capability assertion is stale or invalid.
        """
        caps = self.get_workspace_capabilities(broker_id)
        if caps.get("is_stale", False):
            raise StaleCapabilityException("Capability assertion is STALE. Revalidation required.")

        order_type = str(order_payload.get("order_type", "")).upper()
        trade_type = str(order_payload.get("trade_type", "")).upper()

        if order_type not in caps["allowed_order_types"]:
            logger.warning("Order type '%s' not permitted by capability resolver for broker %s", order_type, broker_id)
            return False

        if trade_type not in caps["allowed_trade_types"]:
            logger.warning("Trade type '%s' not permitted by capability resolver for broker %s", trade_type, broker_id)
            return False

        return True

    def mark_capabilities_stale(self, broker_id: str) -> None:
        """Marks capabilities as stale forcing UI revalidation."""
        caps = self.get_workspace_capabilities(broker_id)
        caps["is_stale"] = True
        self._cached_capabilities[broker_id] = caps
