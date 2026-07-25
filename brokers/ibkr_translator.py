# brokers/ibkr_translator.py
"""
Interactive Brokers (IBKR) Translation Boundary for NexTrade (Sub-Phase 4B).
Translates between NexTrade canonical broker domain models (BrokerOrderRequest/BrokerOrderResult)
and IBKR-compatible order/contract parameter representations.
Zero direct dependencies on external IBKR SDK libraries (ibapi / ib_insync).
"""
from typing import Dict, Any, Tuple
from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderModificationRequest,
    BrokerOrderResult,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerOrderStatus,
)


class IBKRTranslator:
    """Translates canonical NexTrade broker payloads into IBKR API parameters and back."""

    @staticmethod
    def to_ibkr_contract_and_order(request: BrokerOrderRequest) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Translates a canonical BrokerOrderRequest into IBKR-compatible
        Contract dictionary and Order dictionary.
        """
        contract = {
            "symbol": request.symbol,
            "secType": "STK",
            "exchange": request.metadata.get("exchange", "SMART"),
            "currency": "USD",
        }

        order_action = "BUY" if request.side == BrokerOrderSide.BUY else "SELL"
        order_type_map = {
            BrokerOrderType.MARKET: "MKT",
            BrokerOrderType.LIMIT: "LMT",
            BrokerOrderType.STOP: "STP",
            BrokerOrderType.STOP_LIMIT: "STP LMT",
            BrokerOrderType.TRAILING_STOP: "TRAIL",
        }
        ibkr_order_type = order_type_map.get(request.order_type, "MKT")

        order = {
            "action": order_action,
            "totalQuantity": request.quantity,
            "orderType": ibkr_order_type,
            "lmtPrice": request.limit_price or 0.0,
            "auxPrice": request.stop_price or 0.0,
            "tif": request.time_in_force.value,
            "orderRef": request.idempotency_key,
        }

        return contract, order

    @staticmethod
    def from_ibkr_execution(
        request: BrokerOrderRequest,
        ibkr_response: Dict[str, Any]
    ) -> BrokerOrderResult:
        """
        Translates an IBKR execution callback dictionary into a canonical BrokerOrderResult.
        """
        ibkr_status = ibkr_response.get("status", "Unknown").upper()

        if ibkr_status in ("FILLED", "COMPLETED"):
            status = BrokerOrderStatus.FILLED
        elif ibkr_status in ("SUBMITTED", "PRESUBMITTED"):
            status = BrokerOrderStatus.SUBMITTED
        elif ibkr_status in ("CANCELLED", "PENDING_CANCEL"):
            status = BrokerOrderStatus.CANCELLED
        elif ibkr_status in ("INACTIVE", "REJECTED"):
            status = BrokerOrderStatus.REJECTED
        else:
            status = BrokerOrderStatus.UNKNOWN

        filled_qty = float(ibkr_response.get("filled", 0.0))
        rem_qty = float(ibkr_response.get("remaining", request.quantity - filled_qty))
        if rem_qty < 0.0:
            rem_qty = 0.0
        avg_price = float(ibkr_response.get("avgFillPrice", 0.0))
        broker_order_id = str(ibkr_response.get("orderId", ibkr_response.get("permId", "")))

        return BrokerOrderResult(
            nextrade_execution_id=request.nextrade_execution_id,
            idempotency_key=request.idempotency_key,
            broker_order_id=broker_order_id if broker_order_id else None,
            status=status,
            filled_quantity=filled_qty,
            remaining_quantity=rem_qty,
            average_fill_price=avg_price,
            error_code=str(ibkr_response.get("errorCode", "")),
            error_message=str(ibkr_response.get("errorMsg", "")),
            requires_reconciliation=(status == BrokerOrderStatus.UNKNOWN)
        )
