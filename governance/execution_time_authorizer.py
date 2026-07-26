"""
NexTrade Phase 5E — Execution-Time Authorizer (Layer 4).

Layer 4 execution authority engine enforcing the core invariant:
'A valid UI order is not necessarily an executable order.'
Evaluates real-time SafetyState, ConnectionState, ORDER_STATE_UNKNOWN, and multi-layer policies right before dispatch.
"""

import time
import logging
from typing import Dict, Any, Tuple, Optional

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from brokers import BrokerProductionGate, DispatchIneligibleException
from brokers.trade_type_matrix import TradeTypeMatrixValidator, InvalidTradeTypeException
from brokers.order_type_certifier import OrderTypeCertifier, InvalidOrderTypeException
from ui_new.capability_bridge import CapabilityEnforcerBridge
from governance.secret_sanitizer import SecretSanitizer

logger = logging.getLogger("ExecutionTimeAuthorizer")


class ExecutionAuthorizationException(Exception):
    """Raised when an order intent fails Layer 4 execution-time authorization."""
    def __init__(self, reason: str, layer: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.reason = reason
        self.layer = layer
        self.details = details or {}
        super().__init__(f"Layer {layer} Execution Authorization Failed: {reason}")


class ExecutionTimeAuthorizer:
    """
    4-Layer Execution Authority Engine enforcing real-time execution clearance.
    """

    def __init__(
        self,
        production_gate: Optional[BrokerProductionGate] = None,
        matrix_validator: Optional[TradeTypeMatrixValidator] = None,
        order_certifier: Optional[OrderTypeCertifier] = None,
        control_plane: Optional[SafetyControlPlane] = None
    ) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.production_gate = production_gate or BrokerProductionGate(control_plane=self.control_plane)
        self.matrix_validator = matrix_validator or TradeTypeMatrixValidator()
        self.order_certifier = order_certifier or OrderTypeCertifier()
        self.capability_bridge = CapabilityEnforcerBridge()

    def authorize_execution_intent(
        self,
        order_payload: Dict[str, Any],
        session_token: str = "auth_valid_session_token_100",
        idempotency_token: str = "idempotency_default",
        tick_size: float = 0.05,
        lot_size: int = 1,
        market_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Evaluates Layers 1 through 4 execution authorization:
        Layer 1: Product & Instrument Eligibility
        Layer 2: Trade Type Matrix Compatibility
        Layer 3: Order Type Semantics (Tick/Lot Size, Trigger Prices)
        Layer 4: Real-time Dispatch Authority (SafetyState, ConnectionState, ORDER_STATE_UNKNOWN)
        """
        sanitized = SecretSanitizer.sanitize_dict(order_payload)
        logger.info("Authorizing 4-Layer execution intent for order: %s", sanitized)

        broker_id = order_payload.get("broker_id", "IBKR")
        instrument_type = order_payload.get("instrument_type", "EQUITY")
        trade_type = order_payload.get("trade_type", "INTRADAY")

        # --- Layer 1 & Layer 2: Instrument & Trade Type Matrix ---
        valid_l1_l2, reason_l1_l2 = self.matrix_validator.validate_product_and_trade_type(
            broker_id=broker_id,
            instrument_type=instrument_type,
            trade_type=trade_type
        )
        if not valid_l1_l2:
            raise ExecutionAuthorizationException(reason_l1_l2, layer="1_2_Matrix")

        # --- Layer 3: Order Type Semantics ---
        valid_l3, reason_l3 = self.order_certifier.validate_order_type_semantics(
            order_payload=order_payload,
            tick_size=tick_size,
            lot_size=lot_size,
            market_price=market_price
        )
        if not valid_l3:
            raise ExecutionAuthorizationException(reason_l3, layer="3_OrderSemantics")

        # --- Layer 4: Real-time Dispatch Authority ---
        # Verifies SafetyControlPlane and BrokerProductionGate multi-variable predicate
        try:
            self.production_gate.verify_pre_dispatch_authority()
        except DispatchIneligibleException as e:
            raise ExecutionAuthorizationException(str(e), layer="4_ExecutionAuthority", details=e.details)

        # Dispatch order via BrokerProductionGate
        dispatch_response = self.production_gate.dispatch_order(order_payload)
        dispatch_response["layer4_authorization"] = "AUTHORIZED_CLEARED"
        return dispatch_response
