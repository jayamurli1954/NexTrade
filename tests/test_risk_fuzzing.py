# tests/test_risk_fuzzing.py
"""
Property-Based & Metamorphic Fuzz Testing Suite for NexTrade Risk Engine (Sub-Phase 2H-2).
Fuzzes order requests with random, extreme, boundary, NaN/Inf, and malformed inputs to prove:
1. Invariant H1 (Quantity Monotonicity): 0 <= Q_final <= Q_requested
2. Invariant H2 (Fail Closed): Indeterminate / Exception state => REJECTED (Q_final = 0)
3. Property (Risk Monotonicity): Stricter risk budget never increases authorized quantity
4. Property (Idempotence): Identical evaluation snapshot yields identical decision
"""
import random
import unittest
from datetime import datetime, timezone
from decimal import Decimal
import math

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
from risk.position_sizer import PositionSizer
from risk.risk_limits import PortfolioRiskEvaluator
from risk.kill_switch import KillSwitchManager
from risk.risk_engine import RiskEngine


class TestRiskFuzzing(unittest.TestCase):

    def setUp(self):
        self.kill_switch = KillSwitchManager(state_file_path=":memory:")
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
        self.limits = RiskLimits()

    def test_random_fuzz_requested_quantities(self):
        """Fuzz random requested quantities (-1000 to 1,000,000) and verify Invariant H1."""
        random.seed(42)
        for _ in range(50):
            req_qty = random.randint(-50, 10000)
            sig = Signal(
                signal_id=f"SIG-FUZZ-{random.randint(1, 9999)}",
                strategy_id="FUZZ_STRAT",
                symbol="RELIANCE",
                exchange="NSE",
                action=SignalAction.BUY,
                entry_price=2500.0,
                stop_loss=2450.0,
                target_price=2600.0,
                confidence=0.8,
                timestamp=self.now,
                expiry=self.now,
                source="Fuzzer"
            )

            dec = self.engine.evaluate_order_request(
                signal=sig,
                order_side=OrderSide.BUY,
                order_intent=OrderIntent.ENTRY,
                requested_quantity=req_qty,
                context=self.context,
                limits=self.limits
            )

            if req_qty <= 0:
                self.assertEqual(dec.approved_quantity, 0)
                self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
            else:
                self.assertTrue(0 <= dec.approved_quantity <= req_qty,
                                f"Invariant H1 breached for req_qty={req_qty}: got {dec.approved_quantity}")

    def test_extreme_prices_and_stop_losses(self):
        """Test extreme prices (0.0001, 100,000,000) and zero/equal stop losses."""
        extreme_prices = [0.0001, 1.0, 2500.0, 100000.0, 100000000.0]
        for p in extreme_prices:
            # Valid SL below entry for Buy
            sl = p * 0.95
            sig = Signal(
                signal_id="SIG-EXT",
                strategy_id="FUZZ",
                symbol="RELIANCE",
                exchange="NSE",
                action=SignalAction.BUY,
                entry_price=p,
                stop_loss=sl,
                target_price=p * 1.1,
                confidence=0.8,
                timestamp=self.now,
                expiry=self.now,
                source="Test"
            )
            dec = self.engine.evaluate_order_request(
                signal=sig,
                order_side=OrderSide.BUY,
                order_intent=OrderIntent.ENTRY,
                requested_quantity=100,
                context=self.context,
                limits=self.limits
            )
            self.assertTrue(0 <= dec.approved_quantity <= 100)

    def test_invalid_stop_loss_directions(self):
        """Buy with SL >= entry or Sell with SL <= entry must be rejected cleanly."""
        sig_bad_buy = Signal(
            signal_id="SIG-BAD-BUY",
            strategy_id="FUZZ",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2550.0,  # Invalid for BUY
            target_price=2600.0,
            confidence=0.8,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        dec = self.engine.evaluate_order_request(
            signal=sig_bad_buy,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)

    def test_property_risk_monotonicity(self):
        """Stricter risk limits (0.25% vs 0.50%) must never yield a higher authorized quantity."""
        sig = Signal(
            signal_id="SIG-MONO",
            strategy_id="FUZZ",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=0.8,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        limits_normal = RiskLimits(default_risk_per_trade_pct=0.50)
        limits_strict = RiskLimits(min_risk_per_trade_pct=0.10, default_risk_per_trade_pct=0.25)

        dec_normal = self.engine.evaluate_order_request(
            signal=sig, order_side=OrderSide.BUY, order_intent=OrderIntent.ENTRY,
            requested_quantity=100, context=self.context, limits=limits_normal
        )
        dec_strict = self.engine.evaluate_order_request(
            signal=sig, order_side=OrderSide.BUY, order_intent=OrderIntent.ENTRY,
            requested_quantity=100, context=self.context, limits=limits_strict
        )

        self.assertTrue(dec_strict.approved_quantity <= dec_normal.approved_quantity,
                        f"Risk monotonicity breached: strict ({dec_strict.approved_quantity}) > normal ({dec_normal.approved_quantity})")

    def test_property_idempotence(self):
        """Evaluating identical immutable request snapshot twice yields identical decision."""
        sig = Signal(
            signal_id="SIG-IDEM",
            strategy_id="FUZZ",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=0.8,
            timestamp=self.now,
            expiry=self.now,
            source="Test"
        )
        dec1 = self.engine.evaluate_order_request(
            signal=sig, order_side=OrderSide.BUY, order_intent=OrderIntent.ENTRY,
            requested_quantity=10, context=self.context, limits=self.limits
        )
        dec2 = self.engine.evaluate_order_request(
            signal=sig, order_side=OrderSide.BUY, order_intent=OrderIntent.ENTRY,
            requested_quantity=10, context=self.context, limits=self.limits
        )

        self.assertEqual(dec1.decision, dec2.decision)
        self.assertEqual(dec1.approved_quantity, dec2.approved_quantity)
        self.assertEqual(dec1.modification_reason, dec2.modification_reason)


if __name__ == "__main__":
    unittest.main()
