# tests/test_risk_engine.py
"""
Unit Test Suite for NexTrade Phase 2E Risk Engine Orchestrator.
Verifies pure orchestration across Phase 2B, 2C, and 2D layers, runtime quantity invariant enforcement,
auditable decision traces, fail-closed exception safety, and RiskDecision immutability.
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from contracts.signal import Signal, SignalAction
from contracts.order import OrderSide
from contracts.position import Position, PositionSide
from contracts.funds import FundsInfo
from contracts.risk import (
    RiskContext,
    RiskLimits,
    OrderIntent,
    RiskDecision,
    RiskDecisionStatus,
)
from risk.position_sizer import PositionSizer, InstrumentInfo, SizingResult, SizingStatus, SizingReason
from risk.risk_limits import PortfolioRiskEvaluator, PortfolioCheckResult
from risk.kill_switch import KillSwitchManager, KillSwitchLevel, CircuitBreakerType, KillSwitchCheckResult
from risk.risk_engine import RiskEngine


class TestRiskEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "kill_switch_state.json")
        self.kill_switch = KillSwitchManager(state_file_path=self.state_file)
        self.sizer = PositionSizer()
        self.portfolio_evaluator = PortfolioRiskEvaluator()

        self.engine = RiskEngine(
            sizer=self.sizer,
            portfolio_evaluator=self.portfolio_evaluator,
            kill_switch_manager=self.kill_switch
        )

        self.now = datetime.now(timezone.utc)
        self.funds = FundsInfo(
            available_cash=100000.0,
            used_margin=0.0,
            available_margin=100000.0,
            total_equity=100000.0
        )
        self.context = RiskContext(funds=self.funds)
        self.limits = RiskLimits(
            default_risk_per_trade_pct=0.50,  # 0.50% risk = ₹500
            max_symbol_exposure_pct=20.0,
            max_sector_exposure_pct=40.0,
            max_open_positions=5,
            max_daily_loss_amount=5000.0
        )

        self.signal_long = Signal(
            signal_id="SIG-101",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,   # Delta SL = 50 -> Raw qty = 10 shares (₹25,000 value > ₹20,000 cap -> 2C caps at 8)
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_flow_modified_by_risk_sizer(self):
        # Requested 100 shares, 2B sizer approves 10 shares based on risk budget
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.MODIFIED)
        self.assertEqual(dec.approved_quantity, 8)  # 2C symbol cap 20% = ₹20,000 / ₹2,500 = 8 shares
        self.assertTrue(dec.is_submittable)

    def test_full_flow_approved(self):
        # Request exact quantity equal to risk authorized quantity (8 shares)
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.APPROVED)
        self.assertEqual(dec.approved_quantity, 8)
        self.assertTrue(dec.is_submittable)

    def test_portfolio_exposure_cap_modification(self):
        # Existing position ₹15,000. Cap ₹20,000. Room = ₹5,000 / ₹2,500 = 2 shares.
        pos = Position(
            position_id="POS-01",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=6,
            average_entry_price=2500.0,
            current_price=2500.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))

        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=ctx,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.MODIFIED)
        self.assertEqual(dec.approved_quantity, 2)  # Cap room = 2 shares

    def test_kill_switch_blocked(self):
        self.kill_switch.trigger_global(reason="Emergency Stop")
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertFalse(dec.is_submittable)

    def test_exit_allowed_during_global_kill_switch(self):
        pos = Position(
            position_id="POS-01",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))
        self.kill_switch.trigger_global(reason="Emergency Stop")

        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.EXIT,
            requested_quantity=50,
            context=ctx,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.APPROVED)
        self.assertEqual(dec.approved_quantity, 50)
        self.assertTrue(dec.is_submittable)

    def test_exit_blocked_when_broker_offline(self):
        pos = Position(
            position_id="POS-01",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))
        self.kill_switch.set_broker_health("ANGEL_ONE", is_available=False)

        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.EXIT,
            requested_quantity=50,
            context=ctx,
            limits=self.limits,
            broker_name="ANGEL_ONE"
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertFalse(dec.is_submittable)

    def test_short_circuit_on_invalid_sizing_input(self):
        # Invalid long stop: Stop > Entry
        sig_bad_stop = Signal(
            signal_id="SIG-102",
            strategy_id="TREND_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2550.0,  # Invalid
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        dec = self.engine.evaluate_order_request(
            signal=sig_bad_stop,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)

    def test_fail_closed_exception_safety(self):
        # Mock sizer that raises an unexpected exception
        mock_sizer = MagicMock()
        mock_sizer.calculate_quantity.side_effect = RuntimeError("Unexpected internal crash")

        err_engine = RiskEngine(
            sizer=mock_sizer,
            portfolio_evaluator=self.portfolio_evaluator,
            kill_switch_manager=self.kill_switch
        )
        dec = err_engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertEqual(dec.modification_reason, "RISK_ENGINE_INTERNAL_ERROR")

    def test_decision_immutability(self):
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        from dataclasses import FrozenInstanceError
        with self.assertRaises((AttributeError, FrozenInstanceError)):
            dec.approved_quantity = 500  # Frozen dataclass mutation must raise error


    def test_determinism(self):
        dec1 = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )
        dec2 = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec1.decision, dec2.decision)
        self.assertEqual(dec1.approved_quantity, dec2.approved_quantity)


if __name__ == "__main__":
    unittest.main()
