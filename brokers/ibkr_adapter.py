# brokers/ibkr_adapter.py
"""
Interactive Brokers (IBKR) Adapter Skeleton for NexTrade (Sub-Phase 4B).
Implements the canonical BrokerAdapter interface using IBKRTranslator and MockIBKRTransport.
Enforces physical separation between core NexTrade models and external IBKR representations.
Zero direct dependencies on external IBKR libraries (ibapi / ib_insync).
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from contracts.broker_adapter_v1 import BrokerAdapter
from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderModificationRequest,
    BrokerOrderResult,
    BrokerOrder,
    BrokerPosition,
    BrokerAccount,
    BrokerOrderStatus,
    BrokerOrderSide,
    BrokerOrderType,
)
from contracts.broker_capabilities import BrokerCapabilities, CapabilityValidator
from contracts.broker_error import (
    BrokerError,
    BrokerErrorType,
    is_pre_submission_error,
    is_post_submission_ambiguous,
)
from brokers.ibkr_translator import IBKRTranslator
from brokers.ibkr_mock import MockIBKRTransport


class IBKRBrokerAdapter(BrokerAdapter):
    """
    Concrete BrokerAdapter implementation for Interactive Brokers.
    Sub-Phase 4B uses MockIBKRTransport for offline contract and failure testing.
    Actual TWS/Gateway socket connection is deferred strictly to Phase 4C.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        transport: Optional[MockIBKRTransport] = None
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.transport = transport or MockIBKRTransport()
        self._orders: Dict[str, BrokerOrder] = {}

    def get_capabilities(self) -> BrokerCapabilities:
        """Return IBKR adapter capabilities matrix."""
        return BrokerCapabilities(
            broker_name="IBKRBrokerAdapter",
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=True,
            supports_stop_limit_orders=True,
            supports_bracket_orders=True,
            supports_trailing_stops=True,
            supports_order_modification=True,
            supports_partial_fills=True,
            supports_fractional_shares=True,
            supports_short_selling=True,
            supports_websocket_events=False,
            max_orders_per_second=50
        )

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        """
        Submits an order to IBKR via IBKRTranslator and transport.
        Returns canonical BrokerOrderResult.
        """
        now = datetime.now(timezone.utc)

        # Layer 1 Capability Validation
        try:
            CapabilityValidator.validate(self.get_capabilities(), request)
        except ValueError as ve:
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.REJECTED,
                error_code="CAPABILITY_VIOLATION",
                error_message=str(ve),
                timestamp=now
            )

        # Translate to IBKR contract and order dictionaries
        contract_dict, order_dict = IBKRTranslator.to_ibkr_contract_and_order(request)

        try:
            # Submit over transport
            ibkr_res = self.transport.place_order(contract_dict, order_dict)
        except TimeoutError as te:
            # Post-submission timeout boundary -> Status UNKNOWN (Invariant E6/E14/E37)
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.UNKNOWN,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                error_code="TIMEOUT",
                error_message=f"IBKR socket timeout post-transmit: {str(te)}",
                requires_reconciliation=True,
                timestamp=now
            )
        except ConnectionError as ce:
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.UNKNOWN,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                error_code="CONNECTION_ERROR",
                error_message=str(ce),
                requires_reconciliation=True,
                timestamp=now
            )
        except Exception as e:
            # Pre-submission failure -> REJECTED
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.REJECTED,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                error_code="BROKER_SUBMIT_ERROR",
                error_message=str(e),
                timestamp=now
            )

        # Translate response back to canonical BrokerOrderResult
        result = IBKRTranslator.from_ibkr_execution(request, ibkr_res)

        # Record in local index
        if result.broker_order_id:
            broker_order = BrokerOrder(
                broker_order_id=result.broker_order_id,
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                filled_quantity=result.filled_quantity,
                remaining_quantity=result.remaining_quantity,
                status=result.status,
                limit_price=request.limit_price,
                stop_price=request.stop_price,
                average_fill_price=result.average_fill_price,
                created_at=now,
                updated_at=now
            )
            self._orders[result.broker_order_id] = broker_order

        return result

    def get_order(self, broker_order_id: str) -> Optional[BrokerOrder]:
        """Fetch current status and fill state of a specific order."""
        return self._orders.get(broker_order_id)

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        """Cancel an open order with IBKR."""
        now = datetime.now(timezone.utc)
        order = self._orders.get(broker_order_id)
        if not order:
            return BrokerOrderResult(
                nextrade_execution_id="INVALID",
                idempotency_key="INVALID",
                broker_order_id=broker_order_id,
                status=BrokerOrderStatus.REJECTED,
                error_code="ORDER_NOT_FOUND",
                error_message=f"IBKR order '{broker_order_id}' not found",
                timestamp=now
            )

        updated_order = BrokerOrder(
            broker_order_id=order.broker_order_id,
            nextrade_execution_id=order.nextrade_execution_id,
            idempotency_key=order.idempotency_key,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            filled_quantity=order.filled_quantity,
            remaining_quantity=0.0,
            status=BrokerOrderStatus.CANCELLED,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            average_fill_price=order.average_fill_price,
            created_at=order.created_at,
            updated_at=now
        )
        self._orders[broker_order_id] = updated_order

        return BrokerOrderResult(
            nextrade_execution_id=order.nextrade_execution_id,
            idempotency_key=order.idempotency_key,
            broker_order_id=broker_order_id,
            status=BrokerOrderStatus.CANCELLED,
            filled_quantity=order.filled_quantity,
            remaining_quantity=0.0,
            average_fill_price=order.average_fill_price,
            timestamp=now
        )

    def modify_order(self, request: BrokerOrderModificationRequest) -> BrokerOrderResult:
        """Modify an existing open order's parameters via typed request model."""
        now = datetime.now(timezone.utc)
        order = self._orders.get(request.broker_order_id)
        if not order:
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key="INVALID",
                broker_order_id=request.broker_order_id,
                status=BrokerOrderStatus.REJECTED,
                error_code="ORDER_NOT_FOUND",
                error_message=f"IBKR order '{request.broker_order_id}' not found",
                timestamp=now
            )

        new_qty = request.new_quantity if request.new_quantity is not None else order.quantity
        new_limit = request.new_limit_price if request.new_limit_price is not None else order.limit_price

        updated_order = BrokerOrder(
            broker_order_id=order.broker_order_id,
            nextrade_execution_id=request.nextrade_execution_id,
            idempotency_key=order.idempotency_key,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=new_qty,
            filled_quantity=order.filled_quantity,
            remaining_quantity=max(0.0, new_qty - order.filled_quantity),
            status=order.status,
            limit_price=new_limit,
            stop_price=order.stop_price,
            average_fill_price=order.average_fill_price,
            created_at=order.created_at,
            updated_at=now
        )
        self._orders[request.broker_order_id] = updated_order

        return BrokerOrderResult(
            nextrade_execution_id=request.nextrade_execution_id,
            idempotency_key=order.idempotency_key,
            broker_order_id=order.broker_order_id,
            status=order.status,
            filled_quantity=order.filled_quantity,
            remaining_quantity=max(0.0, new_qty - order.filled_quantity),
            average_fill_price=order.average_fill_price,
            timestamp=now
        )

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """Fetch position state."""
        return None

    def get_account(self) -> BrokerAccount:
        """Fetch account state."""
        return BrokerAccount(
            account_id=f"IBKR-PAPER-{self.client_id}",
            currency="USD",
            total_equity=100000.0,
            buying_power=400000.0,
            cash_balance=100000.0,
            is_live=False
        )

    def get_open_orders(self) -> List[BrokerOrder]:
        """Fetch open orders."""
        return [
            o for o in self._orders.values()
            if o.status in (BrokerOrderStatus.SUBMITTED, BrokerOrderStatus.ACKNOWLEDGED, BrokerOrderStatus.PARTIALLY_FILLED)
        ]

    def health_check(self) -> Dict[str, Any]:
        """Check adapter health."""
        return {
            "status": "HEALTHY" if self.transport.is_connected else "DEGRADED",
            "is_connected": self.transport.is_connected,
            "broker_name": "IBKRBrokerAdapter",
            "open_orders_count": len(self.get_open_orders()),
            "is_live": False
        }
