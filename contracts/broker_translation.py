# contracts/broker_translation.py
"""
Domain Translation Layer for NexTrade (Sub-Phase 4B).
Translates between NexTrade core execution contracts (ExecutionRequest/ExecutionResult)
and canonical broker integration domain models (BrokerOrderRequest/BrokerOrderResult).

Guarantees:
- One-way translation at boundary (ExecutionRequest -> BrokerOrderRequest).
- Normalization & reverse translation at return boundary (BrokerOrderResult -> ExecutionResult).
- Lineage preservation (nextrade_execution_id, idempotency_key, risk_decision_id).
- Zero dependency of concrete BrokerAdapter on Phase 3 ExecutionRequest/ExecutionResult models.
"""
from typing import Dict, Any, Optional
import uuid

from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerOrderStatus,
    BrokerTimeInForce,
)


def to_broker_order_request(request: ExecutionRequest) -> BrokerOrderRequest:
    """
    Translates an immutable ExecutionRequest (Phase 3 core model) into a
    BrokerOrderRequest (canonical broker integration model).
    """
    if not isinstance(request, ExecutionRequest):
        raise ValueError(f"Expected ExecutionRequest instance, got {type(request).__name__}")

    # Map OrderSide to BrokerOrderSide
    side_str = request.order_side.value if hasattr(request.order_side, "value") else str(request.order_side)
    side = BrokerOrderSide.BUY if side_str.upper() == "BUY" else BrokerOrderSide.SELL

    # Map order_type to BrokerOrderType
    order_type_str = (request.order_type or "MARKET").upper()
    if order_type_str == "LIMIT":
        order_type = BrokerOrderType.LIMIT
    elif order_type_str == "STOP":
        order_type = BrokerOrderType.STOP
    elif order_type_str == "STOP_LIMIT":
        order_type = BrokerOrderType.STOP_LIMIT
    elif order_type_str == "TRAILING_STOP":
        order_type = BrokerOrderType.TRAILING_STOP
    else:
        order_type = BrokerOrderType.MARKET

    return BrokerOrderRequest(
        nextrade_execution_id=request.execution_request_id,
        idempotency_key=request.idempotency_key,
        symbol=request.symbol,
        side=side,
        order_type=order_type,
        quantity=float(request.execution_quantity),
        limit_price=request.limit_price,
        time_in_force=BrokerTimeInForce.DAY,
        metadata={
            "risk_decision_id": request.risk_decision_id,
            "signal_id": request.signal_id,
            "strategy_id": request.strategy_id,
            "exchange": request.exchange,
        }
    )


def map_broker_status_to_execution_status(status: BrokerOrderStatus) -> ExecutionStatus:
    """Map canonical BrokerOrderStatus enum to ExecutionStatus enum."""
    if status == BrokerOrderStatus.FILLED:
        return ExecutionStatus.FILLED
    elif status == BrokerOrderStatus.PARTIALLY_FILLED:
        return ExecutionStatus.PARTIALLY_FILLED
    elif status == BrokerOrderStatus.SUBMITTED:
        return ExecutionStatus.SUBMITTED
    elif status == BrokerOrderStatus.ACKNOWLEDGED:
        return ExecutionStatus.AUTHORIZED
    elif status == BrokerOrderStatus.CANCELLED:
        return ExecutionStatus.CANCELLED
    elif status == BrokerOrderStatus.EXPIRED:
        return ExecutionStatus.EXPIRED
    elif status == BrokerOrderStatus.REJECTED:
        return ExecutionStatus.REJECTED
    elif status == BrokerOrderStatus.UNKNOWN:
        return ExecutionStatus.UNKNOWN
    else:
        return ExecutionStatus.UNKNOWN


def to_execution_result(
    request: ExecutionRequest,
    broker_result: BrokerOrderResult,
    execution_id: Optional[str] = None
) -> ExecutionResult:
    """
    Normalizes and translates a BrokerOrderResult (canonical broker result)
    back into an immutable ExecutionResult (Phase 3 core model).
    """
    if not isinstance(request, ExecutionRequest):
        raise ValueError(f"Expected ExecutionRequest instance, got {type(request).__name__}")
    if not isinstance(broker_result, BrokerOrderResult):
        raise ValueError(f"Expected BrokerOrderResult instance, got {type(broker_result).__name__}")

    exec_status = map_broker_status_to_execution_status(broker_result.status)
    exec_id = execution_id or f"EXEC-{uuid.uuid4().hex[:12]}"

    filled_qty = int(broker_result.filled_quantity)
    rem_qty = int(request.execution_quantity - filled_qty)
    if rem_qty < 0:
        rem_qty = 0

    rejection_reason = None
    if broker_result.error_message or broker_result.error_code:
        rejection_reason = f"[{broker_result.error_code}] {broker_result.error_message}".strip()

    return ExecutionResult(
        execution_id=exec_id,
        execution_request_id=request.execution_request_id,
        risk_decision_id=request.risk_decision_id,
        status=exec_status,
        requested_quantity=request.requested_quantity,
        execution_quantity=request.execution_quantity,
        filled_quantity=filled_qty,
        remaining_quantity=rem_qty,
        average_fill_price=broker_result.average_fill_price,
        broker_order_id=broker_result.broker_order_id,
        rejection_reason=rejection_reason,
        timestamp=broker_result.timestamp
    )
