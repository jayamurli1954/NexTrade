# tests/test_risk_failure_injection.py
"""
Failure Injection & Fault-Closed Testing Suite for NexTrade Risk Engine (Sub-Phase 2H-3).
Simulates component crashes, unexpected exceptions, and fault conditions across 2B, 2C, and 2D
to verify Invariant H2 (Fail Closed): Any exception yields status REJECTED and Q_final = 0.
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from contracts.signal import Signal, SignalAction
from contracts.order import OrderSide
from contracts.funds import FundsInfo
from contracts.risk import (
    RiskContext,
    RiskLimits,
    OrderIntent,
    RiskDecisionStatus,
)
from risk.position_sizer import PositionSizer
from risk.risk_limits import PortfolioRiskEvaluator
from risk.kill_switch import KillSwitchManager
from risk.risk_engine import RiskEngine


class TestRiskFailureInjection(unittest.TestCase):

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

        self.signal = Signal(
            signal_id="SIG-INJ-01",
            strategy_id="FAULT_STRAT",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=0.85,
            timestamp=self.now,
            expiry=self.now,
            source="FailureInjector"
        )

    def test_position_sizer_exception_fail_closed(self):
        """Simulate unexpected crash in PositionSizer."""
        mock_sizer = MagicMock()
        mock_sizer.calculate_quantity.side_effect = RuntimeError("Sizer math divide-by-zero simulated crash")

        err_engine = RiskEngine(
            sizer=mock_sizer,
            portfolio_evaluator=self.portfolio_evaluator,
            kill_switch_manager=self.kill_switch
        )

        dec = err_engine.evaluate_order_request(
            signal=self.signal,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )

        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertEqual(dec.modification_reason, "RISK_ENGINE_INTERNAL_ERROR")

    def test_portfolio_evaluator_exception_fail_closed(self):
        """Simulate unexpected crash in PortfolioRiskEvaluator."""
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate_portfolio_risk.side_effect = KeyError("Missing sector mapping key crash")

        err_engine = RiskEngine(
            sizer=self.sizer,
            portfolio_evaluator=mock_evaluator,
            kill_switch_manager=self.kill_switch
        )

        dec = err_engine.evaluate_order_request(
            signal=self.signal,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )

        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertEqual(dec.modification_reason, "RISK_ENGINE_INTERNAL_ERROR")

    def test_kill_switch_exception_fail_closed(self):
        """Simulate unexpected crash in KillSwitchManager."""
        mock_ks = MagicMock()
        mock_ks.evaluate_kill_switch.side_effect = OSError("Disk read I/O error on kill switch state")

        err_engine = RiskEngine(
            sizer=self.sizer,
            portfolio_evaluator=self.portfolio_evaluator,
            kill_switch_manager=mock_ks
        )

        dec = err_engine.evaluate_order_request(
            signal=self.signal,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )

        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertEqual(dec.modification_reason, "RISK_ENGINE_INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
