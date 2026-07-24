# tests/test_broker_contract.py
"""
Unit Test Suite for NexTrade Phase 1B BrokerInterface & Error Abstraction.
Tests MockBroker compliance, idempotency, order modifications, and exception hierarchy.
"""
import unittest
from datetime import datetime, timezone
from typing import List, Optional, Dict

from contracts.order import Order, OrderSide, OrderType, OrderStatus, OrderModification
from contracts.trade import Trade, TradeType
from contracts.position import Position, PositionSide, PositionStatus
from contracts.funds import FundsInfo
from contracts.broker import (
    BrokerInterface,
    BrokerError,
    InsufficientFundsError,
    OrderNotFoundError,
    NetworkError,
    OrderValidationError,
    BrokerAuthenticationError,
)


class MockBroker(BrokerInterface):
    """
    Mock Broker implementation used to test BrokerInterface contract compliance.
    """

    def __init__(self, initial_cash: float = 100000.0):
        self.cash = initial_cash
        self.used_margin = 0.0
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.processed_idempotency_keys: Dict[str, str] = {}  # key -> order_id

    def place_order(self, order: Order, idempotency_key: Optional[str] = None) -> Order:
        if idempotency_key and idempotency_key in self.processed_idempotency_keys:
            existing_id = self.processed_idempotency_keys[idempotency_key]
            return self.orders[existing_id]

        req_margin = order.quantity * (order.limit_price or 100.0)
        if req_margin > (self.cash - self.used_margin):
            raise InsufficientFundsError(
                f"Insufficient funds: Required ₹{req_margin:.2f}, Available ₹{self.cash - self.used_margin:.2f}"
            )

        order.broker_order_id = f"BROKER-{order.order_id}"
        order.update_status(OrderStatus.SUBMITTED)
        self.orders[order.order_id] = order

        if idempotency_key:
            self.processed_idempotency_keys[idempotency_key] = order.order_id

        return order

    def cancel_order(self, order_id: str) -> Order:
        if order_id not in self.orders:
            raise OrderNotFoundError(f"Order ID '{order_id}' not found")
        order = self.orders[order_id]
        order.update_status(OrderStatus.CANCELLED)
        return order

    def modify_order(self, order_id: str, changes: OrderModification) -> Order:
        if order_id not in self.orders:
            raise OrderNotFoundError(f"Order ID '{order_id}' not found")
        order = self.orders[order_id]
        if changes.new_quantity is not None:
            order.quantity = changes.new_quantity
        if changes.new_limit_price is not None:
            order.limit_price = changes.new_limit_price
        if changes.new_stop_price is not None:
            order.stop_price = changes.new_stop_price
        if changes.new_time_in_force is not None:
            order.time_in_force = changes.new_time_in_force
        order.updated_at = datetime.now(timezone.utc)
        return order

    def get_order_status(self, order_id: str) -> Order:
        if order_id not in self.orders:
            raise OrderNotFoundError(f"Order ID '{order_id}' not found")
        return self.orders[order_id]

    def get_open_orders(self) -> List[Order]:
        return [
            o for o in self.orders.values()
            if o.status in (OrderStatus.CREATED, OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED)
        ]

    def get_positions(self) -> List[Position]:
        return list(self.positions.values())

    def get_account_funds(self) -> FundsInfo:
        return FundsInfo(
            available_cash=self.cash - self.used_margin,
            used_margin=self.used_margin,
            available_margin=self.cash - self.used_margin,
            total_equity=self.cash
        )

    def get_trades(self, order_id: Optional[str] = None) -> List[Trade]:
        if order_id:
            return [t for t in self.trades if t.order_id == order_id]
        return list(self.trades)


class TestBrokerInterfaceContract(unittest.TestCase):
    def setUp(self):
        self.broker = MockBroker(initial_cash=100000.0)

    def test_place_order_and_idempotency(self):
        order = Order(
            order_id="ORD-101",
            strategy_id="STRAT_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=2500.0
        )
        # First placement
        placed = self.broker.place_order(order, idempotency_key="KEY-001")
        self.assertEqual(placed.status, OrderStatus.SUBMITTED)
        self.assertEqual(placed.broker_order_id, "BROKER-ORD-101")

        # Retry with same idempotency key
        retry_placed = self.broker.place_order(order, idempotency_key="KEY-001")
        self.assertEqual(retry_placed.order_id, "ORD-101")
        self.assertEqual(len(self.broker.get_open_orders()), 1)

    def test_insufficient_funds_exception(self):
        huge_order = Order(
            order_id="ORD-102",
            strategy_id="STRAT_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1000,
            limit_price=2500.0  # Requires 2,500,000 > 100,000 cash
        )
        with self.assertRaises(InsufficientFundsError):
            self.broker.place_order(huge_order)

    def test_cancel_order(self):
        order = Order(
            order_id="ORD-103",
            strategy_id="STRAT_01",
            symbol="INFY",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=5,
            limit_price=1600.0
        )
        self.broker.place_order(order)
        cancelled = self.broker.cancel_order("ORD-103")
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)

        # Cancel non-existent order
        with self.assertRaises(OrderNotFoundError):
            self.broker.cancel_order("ORD-999")

    def test_modify_order(self):
        order = Order(
            order_id="ORD-104",
            strategy_id="STRAT_01",
            symbol="TCS",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=3900.0
        )
        self.broker.place_order(order)
        mod = OrderModification(new_quantity=15, new_limit_price=3950.0)
        modified = self.broker.modify_order("ORD-104", mod)
        self.assertEqual(modified.quantity, 15)
        self.assertEqual(modified.limit_price, 3950.0)

    def test_account_funds(self):
        funds = self.broker.get_account_funds()
        self.assertIsInstance(funds, FundsInfo)
        self.assertEqual(funds.available_cash, 100000.0)
        self.assertEqual(funds.as_of.tzinfo, timezone.utc)

    def test_exception_hierarchy(self):
        self.assertTrue(issubclass(InsufficientFundsError, BrokerError))
        self.assertTrue(issubclass(OrderNotFoundError, BrokerError))
        self.assertTrue(issubclass(NetworkError, BrokerError))
        self.assertTrue(issubclass(OrderValidationError, BrokerError))
        self.assertTrue(issubclass(BrokerAuthenticationError, BrokerError))


if __name__ == "__main__":
    unittest.main()
