# tests/test_position_sizer.py
"""
Unit Test Suite for NexTrade Phase 2B Position Sizing Engine.
Tests risk calculations, Decimal precision, directional stop validation, lot size rounding,
position reduction caps, and minimum economic trade value guards.
"""
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from contracts.signal import Signal, SignalAction
from contracts.order import OrderSide
from contracts.position import Position, PositionSide
from contracts.funds import FundsInfo
from contracts.risk import RiskContext, RiskLimits, OrderIntent
from risk.position_sizer import (
    PositionSizer,
    InstrumentInfo,
    MarginConstraint,
    SizingStatus,
    SizingReason,
)


class TestPositionSizer(unittest.TestCase):

    def setUp(self):
        self.sizer = PositionSizer()
        self.now = datetime.now(timezone.utc)
        self.funds = FundsInfo(
            available_cash=100000.0,
            used_margin=0.0,
            available_margin=100000.0,
            total_equity=100000.0
        )
        self.context = RiskContext(funds=self.funds)
        self.limits = RiskLimits(default_risk_per_trade_pct=0.50)  # 0.50% risk

        self.signal_long = Signal(
            signal_id="SIG-001",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,    # Delta SL = 50
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )

    def test_basic_risk_sizing(self):
        # 100,000 equity * 0.50% = 500 risk budget / 50 stop distance = 10 shares
        res = self.sizer.calculate_quantity(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(res.status, SizingStatus.PARTIALLY_SIZED)
        self.assertEqual(res.approved_quantity, 10)
        self.assertEqual(res.risk_amount, Decimal("500.0"))
        self.assertEqual(res.stop_loss_distance, Decimal("50.0"))

    def test_price_tick_alignment(self):
        sig_unaligned = Signal(
            signal_id="SIG-002",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.03,  # Misaligned to 0.05 tick
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        res = self.sizer.calculate_quantity(
            signal=sig_unaligned,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(res.status, SizingStatus.INVALID_INPUT)
        self.assertEqual(res.reason_code, SizingReason.PRICE_NOT_TICK_ALIGNED)

    def test_directional_stop_validation(self):
        # Long entry with stop loss ABOVE entry price
        sig_bad_stop = Signal(
            signal_id="SIG-003",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2550.0,  # Invalid: stop loss > entry for Long
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        res = self.sizer.calculate_quantity(
            signal=sig_bad_stop,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(res.status, SizingStatus.INVALID_INPUT)
        self.assertEqual(res.reason_code, SizingReason.INVALID_STOP_DIRECTION)

    def test_lot_size_rounding(self):
        # NIFTY Futures / Derivative lot size = 250
        inst = InstrumentInfo(symbol="NIFTY", exchange="NFO", lot_size=250)
        sig_nifty = Signal(
            signal_id="SIG-004",
            strategy_id="TREND_01",
            symbol="NIFTY",
            exchange="NFO",
            action=SignalAction.BUY,
            entry_price=22000.0,
            stop_loss=21900.0,  # Delta SL = 100
            target_price=22200.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        # Large equity ₹10,000,000 * 0.50% = 50,000 risk / 100 SL = 500 raw qty -> 2 lots of 250 = 500
        big_funds = FundsInfo(available_cash=20000000.0, used_margin=0.0, available_margin=20000000.0, total_equity=10000000.0)

        ctx = RiskContext(funds=big_funds)
        res = self.sizer.calculate_quantity(
            signal=sig_nifty,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=1000,
            context=ctx,
            limits=self.limits,
            instrument=inst
        )
        self.assertEqual(res.approved_quantity, 500)
        self.assertEqual(res.approved_quantity % inst.lot_size, 0)

    def test_risk_size_below_minimum_lot(self):
        # Raw risk quantity is 10, but lot size is 250
        inst = InstrumentInfo(symbol="NIFTY", exchange="NFO", lot_size=250)
        res = self.sizer.calculate_quantity(
            signal=self.signal_long,  # Raw qty = 10
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits,
            instrument=inst
        )
        self.assertEqual(res.status, SizingStatus.REJECTED)
        self.assertEqual(res.reason_code, SizingReason.RISK_SIZE_BELOW_MINIMUM_LOT)
        self.assertEqual(res.approved_quantity, 0)

    def test_reduce_intent_capped_by_position(self):
        pos = Position(
            position_id="POS-01",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        ctx_with_pos = RiskContext(funds=self.funds, open_positions=(pos,))

        # Request REDUCE 100 shares, but position has only 50
        res = self.sizer.calculate_quantity(
            signal=self.signal_long,
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.REDUCE,
            requested_quantity=100,
            context=ctx_with_pos,
            limits=self.limits
        )
        self.assertEqual(res.approved_quantity, 50)
        self.assertEqual(res.reason_code, SizingReason.REQUEST_EXCEEDS_POSITION)

    def test_exit_intent_authorizes_full_position(self):
        pos = Position(
            position_id="POS-01",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        ctx_with_pos = RiskContext(funds=self.funds, open_positions=(pos,))

        res = self.sizer.calculate_quantity(
            signal=self.signal_long,
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.EXIT,
            requested_quantity=50,
            context=ctx_with_pos,
            limits=self.limits
        )
        self.assertEqual(res.status, SizingStatus.SIZED)
        self.assertEqual(res.approved_quantity, 50)

    def test_minimum_economic_trade_value_guard(self):
        # Trade value ₹300 < ₹500 minimum
        sig_cheap = Signal(
            signal_id="SIG-005",
            strategy_id="TREND_01",
            symbol="PENNY",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=10.0,
            stop_loss=9.0,      # SL dist = 1 -> Raw qty = 500 -> Trade val = 500 * 10 = 5000 (Passes)
            target_price=12.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        inst_min_val = InstrumentInfo(symbol="PENNY", exchange="NSE", minimum_economic_trade_value=Decimal("10000.0"))
        res = self.sizer.calculate_quantity(
            signal=sig_cheap,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits,
            instrument=inst_min_val
        )
        self.assertEqual(res.status, SizingStatus.REJECTED)
        self.assertEqual(res.reason_code, SizingReason.BELOW_MINIMUM_TRADE_VALUE)
        self.assertEqual(res.approved_quantity, 0)

    def test_sizing_determinism(self):
        res1 = self.sizer.calculate_quantity(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        res2 = self.sizer.calculate_quantity(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(res1.status, res2.status)
        self.assertEqual(res1.approved_quantity, res2.approved_quantity)
        self.assertEqual(res1.risk_amount, res2.risk_amount)


if __name__ == "__main__":
    unittest.main()
