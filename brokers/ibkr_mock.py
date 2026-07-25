# brokers/ibkr_mock.py
"""
Mocked Transport Layer for Interactive Brokers (Sub-Phase 4B).
Simulates IBKR TWS / Gateway socket communication for unit testing without live network connections.
Allows injecting simulated timeouts, rate limits, pre-submission errors, and partial fills.
"""
from typing import Dict, Any, Optional
import uuid


class MockIBKRTransport:
    """
    Mocked IBKR Transport interface simulating API request/response cycles offline.
    """

    def __init__(self):
        self.is_connected = True
        self.simulated_failure_mode: Optional[str] = None
        self.next_order_id = 1001

    def set_simulated_failure(self, mode: Optional[str]) -> None:
        """
        Configure mock failure injection.
        Modes: 'TIMEOUT', 'PRE_SUBMIT_REJECT', 'RATE_LIMIT', 'DISCONNECT'
        """
        self.simulated_failure_mode = mode

    def connect(self, host: str, port: int, client_id: int) -> bool:
        """Simulate connection to IBKR Gateway."""
        if self.simulated_failure_mode == "DISCONNECT":
            self.is_connected = False
            return False
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Simulate disconnect."""
        self.is_connected = False

    def place_order(self, contract: Dict[str, Any], order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate placing an order over IBKR transport socket.
        """
        if not self.is_connected:
            raise ConnectionError("MockIBKRTransport is not connected")

        if self.simulated_failure_mode == "TIMEOUT":
            raise TimeoutError("Mock IBKR Transport socket timeout post-transmit")

        if self.simulated_failure_mode == "PRE_SUBMIT_REJECT":
            return {
                "orderId": 0,
                "status": "REJECTED",
                "filled": 0.0,
                "remaining": order.get("totalQuantity", 0.0),
                "avgFillPrice": 0.0,
                "errorCode": "201",
                "errorMsg": "Order rejected: Insufficient margin in account"
            }

        if self.simulated_failure_mode == "RATE_LIMIT":
            return {
                "orderId": 0,
                "status": "REJECTED",
                "filled": 0.0,
                "remaining": order.get("totalQuantity", 0.0),
                "avgFillPrice": 0.0,
                "errorCode": "162",
                "errorMsg": "Pacing violation: Historical data request / order rate limit exceeded"
            }

        # Default clean execution
        order_id = self.next_order_id
        self.next_order_id += 1
        qty = float(order.get("totalQuantity", 1.0))
        price = float(order.get("lmtPrice") or 100.0)

        return {
            "orderId": order_id,
            "status": "FILLED",
            "filled": qty,
            "remaining": 0.0,
            "avgFillPrice": price,
            "errorCode": "",
            "errorMsg": ""
        }
