# brokers/paper_adapter.py
"""
Paper Broker Adapter for NexTrade (Sub-Phase 4B).
Refactored to inherit from the canonical BrokerAdapter abstract interface
and implement typed domain models (BrokerOrderRequest, BrokerOrderResult, BrokerOrderModificationRequest)
while retaining full backward compatibility with Phase 3 execution methods.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from contracts.broker import BrokerInterface
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
from contracts.broker_error import BrokerError, BrokerErrorType, classify_error_to_status
from contracts.order import Order, OrderSide, OrderType, OrderStatus
from contracts.position import Position, PositionSide
from contracts.funds import FundsInfo
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from order_manager.paper_trader import PaperTrader


class PaperBrokerAdapter(BrokerAdapter, BrokerInterface):
    """
    Adapter implementing canonical BrokerAdapter interface over PaperTrader simulator.
    """

    def __init__(self, paper_trader: Optional[PaperTrader] = None):
        # E13: Pure paper trader simulator, zero live broker endpoints
        self.paper_trader = paper_trader or PaperTrader()
        self._orders: Dict[str, BrokerOrder] = {}

    def get_capabilities(self) -> BrokerCapabilities:
        """Return paper adapter capabilities matrix."""
        return BrokerCapabilities(
            broker_name="PaperBrokerAdapter",
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=True,
            supports_stop_limit_orders=True,
            supports_bracket_orders=False,
            supports_trailing_stops=False,
            supports_order_modification=True,
            supports_partial_fills=True,
            supports_fractional_shares=True,
            supports_short_selling=True,
            supports_websocket_events=False,
            max_orders_per_second=1000
        )

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        """
        Canonical Sub-Phase 4B order submission interface.
        Operates on BrokerOrderRequest payload.
        """
        now = datetime.now(timezone.utc)
        
        # Layer 1 & 2 Capability Validation
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

        try:
            action = "BUY" if request.side == BrokerOrderSide.BUY else "SELL"
            price = request.limit_price if request.limit_price else 100.0

            res_dict = self.paper_trader.execute_order(
                symbol=request.symbol,
                action=action,
                quantity=request.quantity,
                price=price
            )
        except TimeoutError as te:
            # Post-submission timeout -> UNKNOWN status (Invariant E14)
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.UNKNOWN,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                error_code="POST_SUBMISSION_TIMEOUT",
                error_message=f"Paper submission timeout: {str(te)}",
                requires_reconciliation=True,
                timestamp=now
            )
        except Exception as e:
            # Pre-submission failure -> REJECTED status (Invariant E15)
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.REJECTED,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                error_code="DETERMINISTIC_BROKER_ERROR",
                error_message=str(e),
                timestamp=now
            )

        if not res_dict.get("success", False):
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key=request.idempotency_key,
                status=BrokerOrderStatus.REJECTED,
                filled_quantity=0.0,
                remaining_quantity=request.quantity,
                error_code="PAPER_REJECTED",
                error_message=res_dict.get("message", "Paper execution rejected"),
                timestamp=now
            )

        pos_data = res_dict.get("position", {})
        trade_id = str(pos_data.get("trade_id", f"PAPER-{uuid.uuid4().hex[:8]}"))
        filled_qty = float(pos_data.get("quantity", pos_data.get("qty", request.quantity)))
        filled_qty = min(max(0.0, filled_qty), request.quantity)
        rem_qty = request.quantity - filled_qty
        avg_price = float(pos_data.get("avg_price", request.limit_price or 100.0))

        status = BrokerOrderStatus.FILLED if rem_qty == 0 else BrokerOrderStatus.PARTIALLY_FILLED

        # Record in internal order index
        broker_order = BrokerOrder(
            broker_order_id=trade_id,
            nextrade_execution_id=request.nextrade_execution_id,
            idempotency_key=request.idempotency_key,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            filled_quantity=filled_qty,
            remaining_quantity=rem_qty,
            status=status,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            average_fill_price=avg_price,
            created_at=now,
            updated_at=now
        )
        self._orders[trade_id] = broker_order

        return BrokerOrderResult(
            nextrade_execution_id=request.nextrade_execution_id,
            idempotency_key=request.idempotency_key,
            broker_order_id=trade_id,
            status=status,
            filled_quantity=filled_qty,
            remaining_quantity=rem_qty,
            average_fill_price=avg_price,
            timestamp=now
        )

    def get_order(self, broker_order_id: str) -> Optional[BrokerOrder]:
        """Fetch current status and fill state of a specific order."""
        return self._orders.get(broker_order_id)

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        """Cancel an open order with the broker."""
        order = self._orders.get(broker_order_id)
        now = datetime.now(timezone.utc)
        if not order:
            return BrokerOrderResult(
                nextrade_execution_id="INVALID",
                idempotency_key="INVALID",
                broker_order_id=broker_order_id,
                status=BrokerOrderStatus.REJECTED,
                error_code="ORDER_NOT_FOUND",
                error_message=f"Order '{broker_order_id}' not found",
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
        """Modify an existing open order's quantity or price parameters."""
        now = datetime.now(timezone.utc)
        order = self._orders.get(request.broker_order_id)
        if not order:
            return BrokerOrderResult(
                nextrade_execution_id=request.nextrade_execution_id,
                idempotency_key="INVALID",
                broker_order_id=request.broker_order_id,
                status=BrokerOrderStatus.REJECTED,
                error_code="ORDER_NOT_FOUND",
                error_message=f"Order '{request.broker_order_id}' not found",
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
        """Fetch current open position for a symbol."""
        positions = self.paper_trader.get_positions()
        pos = positions.get(symbol)
        if not pos:
            return None
        return BrokerPosition(
            symbol=symbol,
            quantity=float(pos.get("quantity", pos.get("qty", 0.0))),
            average_entry_price=float(pos.get("avg_price", 0.0)),
            current_market_price=float(pos.get("current_price", 0.0)),
            unrealized_pnl=float(pos.get("pnl", 0.0))
        )

    def get_account(self) -> BrokerAccount:
        """Fetch broker account equity, buying power, and cash balance."""
        summary = self.paper_trader.get_summary()
        return BrokerAccount(
            account_id="PAPER-ACCT-001",
            currency="USD",
            total_equity=float(summary.get("portfolio_value", 100000.0)),
            buying_power=float(summary.get("available_margin", 100000.0)),
            cash_balance=float(summary.get("current_cash", 100000.0)),
            margin_used=float(summary.get("used_margin", 0.0)),
            is_live=False
        )

    def get_open_orders(self) -> List[BrokerOrder]:
        """Fetch all open/active orders."""
        return [
            o for o in self._orders.values()
            if o.status in (BrokerOrderStatus.SUBMITTED, BrokerOrderStatus.ACKNOWLEDGED, BrokerOrderStatus.PARTIALLY_FILLED)
        ]

    def health_check(self) -> Dict[str, Any]:
        """Return health and state summary."""
        return {
            "status": "HEALTHY",
            "is_connected": True,
            "broker_name": "PaperBrokerAdapter",
            "open_orders_count": len(self.get_open_orders()),
            "is_live": False
        }

    # =========================================================================
    # Phase 3 Backward-Compatibility Methods
    # =========================================================================

    def execute_order(self, request: ExecutionRequest) -> ExecutionResult:
        """Phase 3 backward-compatible entry point wrapping to_broker_order_request/submit_order."""
        from contracts.broker_translation import to_broker_order_request, to_execution_result
        now = datetime.now(timezone.utc)
        exec_id = f"EXEC-{uuid.uuid4().hex[:12].upper()}"

        if not request or request.execution_quantity <= 0:
            return ExecutionResult(
                execution_id=exec_id,
                execution_request_id=request.execution_request_id if request else "INVALID",
                risk_decision_id=request.risk_decision_id if request else "INVALID",
                status=ExecutionStatus.REJECTED,
                requested_quantity=request.requested_quantity if request else 0,
                execution_quantity=request.execution_quantity if request else 0,
                filled_quantity=0,
                remaining_quantity=request.execution_quantity if request else 0,
                average_fill_price=0.0,
                rejection_reason="PRE_SUBMISSION_ERROR: Invalid execution quantity or null request",
                timestamp=now
            )

        broker_req = to_broker_order_request(request)
        broker_res = self.submit_order(broker_req)
        return to_execution_result(request, broker_res, execution_id=exec_id)

    def place_order(self, order: Order, idempotency_key: Optional[str] = None) -> Order:
        """BrokerInterface protocol implementation for place_order."""
        action = "BUY" if order.side == OrderSide.BUY else "SELL"
        res = self.paper_trader.execute_order(
            symbol=order.symbol,
            action=action,
            quantity=order.quantity,
            price=order.price or 100.0,
            stoploss=order.stop_price
        )
        trade_id = res.get("position", {}).get("trade_id", f"PAPER-{uuid.uuid4().hex[:8]}")
        return Order(
            order_id=order.order_id,
            broker_order_id=str(trade_id),
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.price,
            status=OrderStatus.FILLED if res.get("success") else OrderStatus.REJECTED,
            filled_quantity=order.quantity if res.get("success") else 0,
            average_price=order.price or 100.0
        )

    def get_order_status(self, order_id: str) -> Order:
        """BrokerInterface protocol implementation for get_order_status."""
        return Order(
            order_id=order_id,
            broker_order_id=order_id,
            symbol="UNKNOWN",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
            status=OrderStatus.FILLED,
            filled_quantity=0,
            average_price=0.0
        )

    def get_positions(self) -> List[Position]:
        """BrokerInterface protocol implementation for get_positions."""
        positions = []
        for sym, pos in self.paper_trader.get_positions().items():
            side = PositionSide.LONG if pos.get("position_type") == "LONG" else PositionSide.SHORT
            positions.append(
                Position(
                    position_id=f"POS-{sym}",
                    strategy_id="PAPER",
                    symbol=sym,
                    exchange="NSE",
                    side=side,
                    quantity=pos.get("quantity", pos.get("qty", 0)),
                    average_entry_price=pos.get("avg_price", 0.0),
                    current_price=pos.get("current_price", 0.0),
                    unrealized_pnl=pos.get("pnl", 0.0)
                )
            )
        return positions

    def get_account_funds(self) -> FundsInfo:
        """BrokerInterface protocol implementation for get_account_funds."""
        summary = self.paper_trader.get_summary()
        return FundsInfo(
            available_cash=summary.get("current_cash", 100000.0),
            used_margin=summary.get("used_margin", 0.0),
            available_margin=summary.get("available_margin", 100000.0),
            total_equity=summary.get("portfolio_value", 100000.0)
        )

    def get_trades(self, order_id: Optional[str] = None) -> List[Any]:
        """BrokerInterface protocol implementation for get_trades."""
        return []

    def query_execution(
        self,
        execution_request_id: Optional[str] = None,
        broker_order_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Sub-Phase 3E query execution implementation."""
        trades = getattr(self.paper_trader, "trades", [])
        for trade in trades:
            t_id = str(trade.get("trade_id", ""))
            if (broker_order_id and t_id == str(broker_order_id)) or (execution_request_id and trade.get("execution_request_id") == execution_request_id):
                return {
                    "broker_order_id": t_id,
                    "status": ExecutionStatus.FILLED,
                    "cumulative_filled_quantity": trade.get("quantity", 0),
                    "average_fill_price": float(trade.get("price", 100.0)),
                    "symbol": trade.get("symbol", ""),
                }
        return None
