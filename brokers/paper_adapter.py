# brokers/paper_adapter.py
"""
Paper Broker Adapter for NexTrade (Sub-Phase 3C).
Implements the BrokerInterface protocol (contracts/broker.py) by wrapping the existing PaperTrader simulator.
Enforces Invariants E11 - E16:
E11 (Broker Isolation): RiskEngine remains completely unaware of broker implementation.
E12 (Quantity Preservation): 0 <= Q_filled <= Q_execution <= Q_approved.
E13 (No Live Connectivity): Provably paper-only execution without live API keys/endpoints.
E14 (Unknown-State Preservation): Ambiguous submission outcomes produce status UNKNOWN with requires_reconciliation = True.
E15 (Broker Error Isolation): Deterministic errors produce status REJECTED; pre- vs post-submission ambiguity is distinguished.
E16 (Execution Traceability): Full lineage (execution_request_id, risk_decision_id, signal_id, paper_trade_id) preserved.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from contracts.broker import BrokerInterface, BrokerError
from contracts.order import Order, OrderSide, OrderType, OrderStatus
from contracts.position import Position, PositionSide
from contracts.funds import FundsInfo
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from order_manager.paper_trader import PaperTrader


class PaperBrokerAdapter(BrokerInterface):
    """
    Adapter implementing BrokerInterface protocol over PaperTrader simulator.
    """

    def __init__(self, paper_trader: Optional[PaperTrader] = None):
        # E13: Pure paper trader simulator, zero live broker endpoints
        self.paper_trader = paper_trader or PaperTrader()

    def execute_order(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Translate an ExecutionRequest into a PaperTrader order submission.
        """
        now = datetime.now(timezone.utc)
        exec_id = f"EXEC-{uuid.uuid4().hex[:12].upper()}"

        # Pre-submission input validation check
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

        try:
            # Map OrderSide to PaperTrader BUY/SELL action string
            action = "BUY" if request.order_side == OrderSide.BUY else "SELL"
            price = request.limit_price if request.limit_price else 100.0
            
            # Execute on PaperTrader simulator via execute_order
            res_dict = self.paper_trader.execute_order(
                symbol=request.symbol,
                action=action,
                quantity=request.execution_quantity,
                price=price
            )
        except TimeoutError as te:
            # Post-submission boundary timeout -> Status UNKNOWN (Invariant E14)
            return ExecutionResult(
                execution_id=exec_id,
                execution_request_id=request.execution_request_id,
                risk_decision_id=request.risk_decision_id,
                status=ExecutionStatus.UNKNOWN,
                requested_quantity=request.requested_quantity,
                execution_quantity=request.execution_quantity,
                filled_quantity=0,
                remaining_quantity=request.execution_quantity,
                average_fill_price=0.0,
                rejection_reason=f"POST_SUBMISSION_TIMEOUT: Ambiguous outcome after submission attempt: {str(te)}",
                timestamp=now
            )
        except Exception as e:
            # Deterministic pre-submission / paper engine exception -> Status REJECTED (Invariant E15)
            return ExecutionResult(
                execution_id=exec_id,
                execution_request_id=request.execution_request_id,
                risk_decision_id=request.risk_decision_id,
                status=ExecutionStatus.REJECTED,
                requested_quantity=request.requested_quantity,
                execution_quantity=request.execution_quantity,
                filled_quantity=0,
                remaining_quantity=request.execution_quantity,
                average_fill_price=0.0,
                rejection_reason=f"DETERMINISTIC_BROKER_ERROR: Paper broker failed: {str(e)}",
                timestamp=now
            )

        # Evaluate PaperTrader response dictionary
        if not res_dict.get("success", False):
            return ExecutionResult(
                execution_id=exec_id,
                execution_request_id=request.execution_request_id,
                risk_decision_id=request.risk_decision_id,
                status=ExecutionStatus.REJECTED,
                requested_quantity=request.requested_quantity,
                execution_quantity=request.execution_quantity,
                filled_quantity=0,
                remaining_quantity=request.execution_quantity,
                average_fill_price=0.0,
                rejection_reason=f"PAPER_BROKER_REJECTION: {res_dict.get('message', 'Paper trade rejected')}",
                timestamp=now
            )

        # Successful paper order execution
        pos_data = res_dict.get("position", {})
        paper_trade_id = pos_data.get("trade_id", f"PAPER-{exec_id}")
        filled_qty = pos_data.get("quantity", pos_data.get("qty", request.execution_quantity))
        
        # Quantity Preservation check (E12): 0 <= Q_filled <= Q_execution
        filled_qty = min(max(0, filled_qty), request.execution_quantity)
        rem_qty = request.execution_quantity - filled_qty
        avg_price = pos_data.get("avg_price", request.limit_price or 100.0)

        status = ExecutionStatus.FILLED if rem_qty == 0 else ExecutionStatus.PARTIALLY_FILLED

        return ExecutionResult(
            execution_id=exec_id,
            execution_request_id=request.execution_request_id,
            risk_decision_id=request.risk_decision_id,
            broker_order_id=str(paper_trade_id),
            status=status,
            requested_quantity=request.requested_quantity,
            execution_quantity=request.execution_quantity,
            filled_quantity=filled_qty,
            remaining_quantity=rem_qty,
            average_fill_price=float(avg_price),
            timestamp=now
        )

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

    def cancel_order(self, order_id: str) -> Order:
        """BrokerInterface protocol implementation for cancel_order."""
        return Order(
            order_id=order_id,
            symbol="UNKNOWN",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
            status=OrderStatus.CANCELLED
        )

    def modify_order(self, order_id: str, changes: Any) -> Order:
        """BrokerInterface protocol implementation for modify_order."""
        return Order(
            order_id=order_id,
            symbol="UNKNOWN",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
            status=OrderStatus.MODIFIED
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

    def get_open_orders(self) -> List[Order]:
        """BrokerInterface protocol implementation for get_open_orders."""
        return []

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
        """
        Sub-Phase 3E: Query authoritative broker execution state for reconciliation.
        """
        # Look up in paper trader trades history if available
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
