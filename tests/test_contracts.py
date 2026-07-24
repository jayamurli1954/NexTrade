# tests/test_contracts.py
"""
Unit Test Suite for NexTrade Phase 1A Canonical Contracts
(Signal, Order, Trade, Position)
"""
import unittest
from datetime import datetime, timedelta, timezone

from contracts.signal import Signal, SignalAction, SignalStatus
from contracts.order import Order, OrderSide, OrderType, OrderStatus, TimeInForce
from contracts.trade import Trade, TradeType
from contracts.position import Position, PositionSide, PositionStatus


class TestSignalContract(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.expiry = self.now + timedelta(hours=2)

    def test_signal_creation_and_immutability(self):
        sig = Signal(
            signal_id="SIG-001",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.expiry,
            source="InvestMitra",
            suggested_quantity=50,
            metadata={"notes": "Bullish breakout"}
        )
        self.assertEqual(sig.signal_id, "SIG-001")
        self.assertEqual(sig.action, SignalAction.BUY)
        self.assertEqual(sig.timestamp.tzinfo, timezone.utc)
        self.assertEqual(sig.metadata["notes"], "Bullish breakout")

        # Verify immutability
        with self.assertRaises((AttributeError, TypeError)):
            sig.confidence = 0.95

        # Verify metadata mutation protection
        with self.assertRaises((AttributeError, TypeError)):
            sig.metadata["notes"] = "Modified"


    def test_signal_expiry(self):
        sig = Signal(
            signal_id="SIG-002",
            strategy_id="MOMENTUM_01",
            symbol="INFY",
            exchange="NSE",
            action=SignalAction.SELL,
            entry_price=1600.0,
            stop_loss=1620.0,
            target_price=1550.0,
            confidence=0.75,
            timestamp=self.now,
            expiry=self.expiry,
            source="NexTrade_Analyzer"
        )
        # Check before expiry
        self.assertFalse(sig.is_expired(self.now + timedelta(hours=1)))
        # Check after expiry
        self.assertTrue(sig.is_expired(self.now + timedelta(hours=3)))

    def test_signal_dict_serialization(self):
        sig = Signal(
            signal_id="SIG-003",
            strategy_id="STAT_ARB_01",
            symbol="TCS",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=4000.0,
            stop_loss=3950.0,
            target_price=4100.0,
            confidence=0.9,
            timestamp=self.now,
            expiry=self.expiry,
            source="InvestMitra"
        )
        d = sig.to_dict()
        self.assertEqual(d["signal_id"], "SIG-003")
        self.assertEqual(d["action"], "BUY")

        restored = Signal.from_dict(d)
        self.assertEqual(restored.signal_id, sig.signal_id)
        self.assertEqual(restored.confidence, sig.confidence)


class TestOrderContract(unittest.TestCase):
    def test_order_lifecycle_and_fills(self):
        order = Order(
            order_id="ORD-001",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=2500.0,
            signal_id="SIG-001"
        )
        self.assertEqual(order.status, OrderStatus.CREATED)
        self.assertEqual(order.filled_quantity, 0)

        # Status update
        order.update_status(OrderStatus.RISK_APPROVED)
        self.assertEqual(order.status, OrderStatus.RISK_APPROVED)

        # First partial fill: 40 shares @ 2495.0
        order.add_fill(40, 2495.0)
        self.assertEqual(order.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(order.filled_quantity, 40)
        self.assertEqual(order.average_fill_price, 2495.0)

        # Second fill: 60 shares @ 2505.0 (Completes order)
        order.add_fill(60, 2505.0)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.filled_quantity, 100)
        self.assertAlmostEqual(order.average_fill_price, 2501.0)

    def test_order_overfill_rejection(self):
        order = Order(
            order_id="ORD-002",
            strategy_id="TREND_01",
            symbol="INFY",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=50
        )
        order.add_fill(30, 1600.0)
        with self.assertRaises(ValueError):
            order.add_fill(30, 1600.0)  # Exceeds total quantity of 50


class TestTradeContract(unittest.TestCase):
    def test_trade_fill_immutability(self):
        trade = Trade(
            trade_id="TRD-001",
            order_id="ORD-001",
            symbol="RELIANCE",
            exchange="NSE",
            side=OrderSide.BUY,
            trade_type=TradeType.ENTRY,
            quantity=40,
            price=2495.0,
            fee=15.0,
            slippage=0.5
        )
        self.assertEqual(trade.trade_id, "TRD-001")
        self.assertEqual(trade.side, OrderSide.BUY)
        self.assertEqual(trade.timestamp.tzinfo, timezone.utc)

        with self.assertRaises((AttributeError, TypeError)):
            trade.price = 2500.0


    def test_trade_dict_serialization(self):
        trade = Trade(
            trade_id="TRD-002",
            order_id="ORD-001",
            symbol="INFY",
            exchange="NSE",
            side=OrderSide.SELL,
            trade_type=TradeType.EXIT,
            quantity=30,
            price=1610.0
        )
        d = trade.to_dict()
        restored = Trade.from_dict(d)
        self.assertEqual(restored.trade_id, trade.trade_id)
        self.assertEqual(restored.side, OrderSide.SELL)


class TestPositionContract(unittest.TestCase):
    def test_position_pnl_and_close(self):
        pos = Position(
            position_id="POS-001",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        self.assertEqual(pos.status, PositionStatus.OPEN)
        self.assertEqual(pos.opened_at.tzinfo, timezone.utc)

        # Market price update
        pos.update_market_price(2520.0)
        self.assertEqual(pos.unrealized_pnl, 1000.0)
        self.assertEqual(pos.realized_pnl, 0.0)

        # Close position @ 2525.0
        pos.close(2525.0)
        self.assertEqual(pos.status, PositionStatus.CLOSED)
        self.assertEqual(pos.realized_pnl, 1250.0)
        self.assertEqual(pos.unrealized_pnl, 0.0)
        self.assertEqual(pos.side, PositionSide.FLAT)
        self.assertIsNotNone(pos.closed_at)


if __name__ == "__main__":
    unittest.main()
