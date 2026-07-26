"""
NexTrade Phase 5E — Order Type Certifier (Layer 3).

Certifies Order Type Semantics (LIMIT, MARKET, SL, SL-M), tick size precision,
lot size multiples, and Stop-Loss trigger rules.
"""

import math
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("OrderTypeCertifier")


class InvalidOrderTypeException(Exception):
    """Raised when order parameters violate Layer 3 order type or price/lot semantics."""
    pass


class OrderTypeCertifier:
    """
    Certifies Layer 3 order semantics: price tick size, lot size multiples,
    Stop-Loss trigger rules, and market order prohibitions.
    """

    SUPPORTED_ORDER_TYPES = {"LIMIT", "MARKET", "SL", "SL-M"}

    def validate_order_type_semantics(
        self,
        order_payload: Dict[str, Any],
        tick_size: float = 0.05,
        lot_size: int = 1,
        market_price: Optional[float] = None,
        market_orders_allowed: bool = True
    ) -> Tuple[bool, str]:
        """
        Validates Layer 3 order semantics for LIMIT, MARKET, SL, and SL-M orders.
        """
        order_type = str(order_payload.get("order_type", "")).upper()
        action = str(order_payload.get("action", "BUY")).upper()
        quantity = int(order_payload.get("quantity", 0))
        price = float(order_payload.get("price", 0.0))
        trigger_price = float(order_payload.get("trigger_price", 0.0))

        if order_type not in self.SUPPORTED_ORDER_TYPES:
            err = f"Order type '{order_type}' is unrecognized or uncertified"
            logger.warning(err)
            return False, err

        # Check Market Order Prohibition
        if order_type in ("MARKET", "SL-M") and not market_orders_allowed:
            err = f"Market orders ({order_type}) are strictly prohibited for this instrument"
            logger.warning(err)
            return False, err

        # Quantity Lot Size Multiple Check
        if quantity <= 0 or (quantity % lot_size != 0):
            err = f"Quantity {quantity} must be a positive multiple of lot size {lot_size}"
            logger.warning(err)
            return False, err

        # Price Tick Size Precision Check for LIMIT and SL orders
        if order_type in ("LIMIT", "SL"):
            if price <= 0.0:
                err = f"Price must be greater than zero for {order_type} orders"
                logger.warning(err)
                return False, err

            # Check tick size multiple: abs(price - round(price/tick_size)*tick_size) < 1e-4
            remainder = abs(price - round(price / tick_size) * tick_size)
            if remainder > 1e-4:
                err = f"Price {price:.2f} is not a valid multiple of tick size {tick_size}"
                logger.warning(err)
                return False, err

        # Stop-Loss Trigger Price Semantics
        if order_type in ("SL", "SL-M"):
            if trigger_price <= 0.0:
                err = f"Trigger price must be specified for {order_type} orders"
                logger.warning(err)
                return False, err

            ref_price = market_price or price
            if ref_price > 0.0:
                if action == "BUY" and trigger_price < ref_price:
                    err = f"Stop-Loss BUY trigger price {trigger_price} must be >= reference price {ref_price}"
                    logger.warning(err)
                    return False, err
                elif action == "SELL" and trigger_price > ref_price:
                    err = f"Stop-Loss SELL trigger price {trigger_price} must be <= reference price {ref_price}"
                    logger.warning(err)
                    return False, err

        return True, "ORDER_TYPE_SEMANTICS_CERTIFIED"

    def certify_order_semantics(self, order_payload: Dict[str, Any], **kwargs) -> None:
        """Certifies order type semantics. Raises InvalidOrderTypeException if invalid."""
        valid, reason = self.validate_order_type_semantics(order_payload, **kwargs)
        if not valid:
            raise InvalidOrderTypeException(reason)
