# brokers/ibkr_client.py
"""
IBKR Sandbox Harness & Transport Engine for NexTrade (Sub-Phase 4C).
Provides an offline, deterministic IBKRSandboxHarness that models full Interactive Brokers
paper trading API behavior, fill processing, order modifications, and failure scenarios.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

from config.ibkr_config import IBKRConfig, validate_sandbox_config


class IBKRSandboxHarness:
    """
    Deterministic Sandbox Harness simulating IBKR TWS/Gateway socket API response cycles offline.
    """

    def __init__(self, config: Optional[IBKRConfig] = None):
        self.config = config or IBKRConfig()
        validate_sandbox_config(self.config, live_trading_enabled=False)

        self.is_connected = True
        self.simulated_mode: Optional[str] = None
        self._next_order_id = 2001
        self.orders: Dict[int, Dict[str, Any]] = {}
        self.fills: List[Dict[str, Any]] = []
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.account_cash = 100000.0
        self.account_equity = 100000.0

    def set_simulated_mode(self, mode: Optional[str]) -> None:
        """
        Configure sandbox failure or fill mode.
        Modes: 'TIMEOUT', 'PRE_SUBMIT_REJECT', 'RATE_LIMIT', 'DISCONNECT', 'PARTIAL_FILL'
        """
        self.simulated_mode = mode

    def connect(self) -> bool:
        """Simulate socket connection to IBKR Paper Gateway."""
        validate_sandbox_config(self.config, live_trading_enabled=False)
        if self.simulated_mode == "DISCONNECT":
            self.is_connected = False
            return False
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Simulate socket disconnection."""
        self.is_connected = False

    def place_order(self, contract: Dict[str, Any], order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate placing an order over IBKR client transport socket.
        """
        if not self.is_connected:
            raise ConnectionError("IBKRSandboxHarness is disconnected")

        if self.simulated_mode == "TIMEOUT":
            raise TimeoutError("IBKR socket read timeout after order transmission")

        if self.simulated_mode == "PRE_SUBMIT_REJECT":
            return {
                "orderId": 0,
                "status": "REJECTED",
                "filled": 0.0,
                "remaining": order.get("totalQuantity", 0.0),
                "avgFillPrice": 0.0,
                "errorCode": "201",
                "errorMsg": "Order rejected: Insufficient margin in paper account"
            }

        if self.simulated_mode == "RATE_LIMIT":
            return {
                "orderId": 0,
                "status": "REJECTED",
                "filled": 0.0,
                "remaining": order.get("totalQuantity", 0.0),
                "avgFillPrice": 0.0,
                "errorCode": "162",
                "errorMsg": "Pacing violation: Order rate limit exceeded (max 50/sec)"
            }

        order_id = self._next_order_id
        self._next_order_id += 1

        total_qty = float(order.get("totalQuantity", 1.0))
        limit_price = float(order.get("lmtPrice") or 100.0)

        if self.simulated_mode == "PARTIAL_FILL":
            filled_qty = float(int(total_qty / 2))
            if filled_qty <= 0:
                filled_qty = 1.0
            remaining_qty = total_qty - filled_qty
            status = "PARTIALLY_FILLED" if remaining_qty > 0 else "FILLED"
        else:
            filled_qty = total_qty
            remaining_qty = 0.0
            status = "FILLED"

        order_record = {
            "orderId": order_id,
            "contract": contract,
            "order": order,
            "status": status,
            "filled": filled_qty,
            "remaining": remaining_qty,
            "avgFillPrice": limit_price,
            "errorCode": "",
            "errorMsg": "",
            "orderRef": order.get("orderRef", "")
        }
        self.orders[order_id] = order_record

        # Update position tracking if fill occurred
        symbol = contract.get("symbol", "UNKNOWN")
        if filled_qty > 0:
            fill_record = {
                "fillId": f"FILL-{uuid.uuid4().hex[:8].upper()}",
                "orderId": order_id,
                "symbol": symbol,
                "quantity": filled_qty,
                "price": limit_price,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.fills.append(fill_record)

            curr_pos = self.positions.get(symbol, {"quantity": 0.0, "avg_price": 0.0})
            old_qty = curr_pos["quantity"]
            new_qty = old_qty + filled_qty
            new_avg = ((old_qty * curr_pos["avg_price"]) + (filled_qty * limit_price)) / new_qty if new_qty > 0 else limit_price
            self.positions[symbol] = {"quantity": new_qty, "avg_price": new_avg, "symbol": symbol}

        return order_record

    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """Simulate order cancellation."""
        if order_id not in self.orders:
            return {
                "orderId": order_id,
                "status": "REJECTED",
                "errorCode": "10135",
                "errorMsg": f"Can't find order with id = {order_id}"
            }

        record = self.orders[order_id]
        record["status"] = "CANCELLED"
        record["remaining"] = 0.0
        return record

    def modify_order(self, order_id: int, new_quantity: Optional[float] = None, new_price: Optional[float] = None) -> Dict[str, Any]:
        """Simulate order modification."""
        if order_id not in self.orders:
            return {
                "orderId": order_id,
                "status": "REJECTED",
                "errorCode": "10135",
                "errorMsg": f"Can't find order with id = {order_id}"
            }

        record = self.orders[order_id]
        if new_quantity is not None:
            record["order"]["totalQuantity"] = new_quantity
            record["remaining"] = max(0.0, new_quantity - record["filled"])
        if new_price is not None:
            record["order"]["lmtPrice"] = new_price
            record["avgFillPrice"] = new_price

        return record

    def query_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Query state of order by IBKR orderId."""
        return self.orders.get(order_id)
