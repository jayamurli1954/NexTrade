"""
NexTrade Phase 5E — Trade Type Matrix Validator (Layer 1 & Layer 2).

Validates Product & Instrument Eligibility (Layer 1) and Trade Type Product Compatibility (Layer 2)
across Broker x Account x Instrument x Trade Type.
"""

import logging
from typing import Dict, Any, Tuple, Set

logger = logging.getLogger("TradeTypeMatrixValidator")


class InvalidTradeTypeException(Exception):
    """Raised when an order specifies an invalid or incompatible trade type."""
    pass


class TradeTypeMatrixValidator:
    """
    Validates Layer 1 (Instrument) and Layer 2 (Trade Type) matrix rules.
    """

    SUPPORTED_INSTRUMENTS = {"EQUITY", "FUTURES", "OPTIONS", "CURRENCY", "COMMODITY"}
    SUPPORTED_TRADE_TYPES = {"INTRADAY", "DELIVERY", "F&O"}

    # Matrix rule mappings
    INSTRUMENT_TRADE_TYPE_MATRIX = {
        "EQUITY": {"INTRADAY", "DELIVERY"},
        "FUTURES": {"INTRADAY", "F&O"},
        "OPTIONS": {"INTRADAY", "F&O"},
        "CURRENCY": {"INTRADAY", "F&O"},
        "COMMODITY": {"INTRADAY", "F&O"},
    }

    def validate_product_and_trade_type(
        self,
        broker_id: str,
        instrument_type: str,
        trade_type: str,
        account_tier: str = "PILOT"
    ) -> Tuple[bool, str]:
        """
        Validates Layer 1 (Instrument) and Layer 2 (Trade Type) eligibility.
        """
        inst_upper = str(instrument_type).upper()
        trade_upper = str(trade_type).upper()

        # Layer 1: Check instrument eligibility
        if inst_upper not in self.SUPPORTED_INSTRUMENTS:
            err = f"Instrument type '{instrument_type}' is not supported by broker '{broker_id}'"
            logger.warning(err)
            return False, err

        # Layer 2: Check trade type eligibility
        if trade_upper not in self.SUPPORTED_TRADE_TYPES:
            err = f"Trade type '{trade_type}' is unrecognized or unsupported"
            logger.warning(err)
            return False, err

        allowed_trade_types = self.INSTRUMENT_TRADE_TYPE_MATRIX.get(inst_upper, set())
        if trade_upper not in allowed_trade_types:
            err = f"Trade type '{trade_upper}' is incompatible with instrument '{inst_upper}' (allowed: {sorted(list(allowed_trade_types))})"
            logger.warning(err)
            return False, err

        return True, "PRODUCT_AND_TRADE_TYPE_VALID"

    def enforce_trade_type_matrix(self, broker_id: str, instrument_type: str, trade_type: str) -> None:
        """Enforces trade type matrix. Raises InvalidTradeTypeException if invalid."""
        valid, reason = self.validate_product_and_trade_type(broker_id, instrument_type, trade_type)
        if not valid:
            raise InvalidTradeTypeException(reason)
