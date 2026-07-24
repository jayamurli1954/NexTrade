# tests/test_security_boundary.py
"""
Security Boundary & Bypass Resistance Test Suite for NexTrade (Sub-Phase 2H-6).
Verifies caller attempts to forge, tamper, or supply arbitrary parameters cannot bypass RiskEngine authorization.
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from contracts.signal import Signal, SignalAction
from contracts.order import OrderSide
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
from risk.execution_gate import ExecutionAuthorizationGate


class TestSecurityBoundary(unittest.TestCase):

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
        self.limits = RiskLimits()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_caller_cannot_override_authorized_quantity(self):
        """Caller supplying 10,000 shares cannot override RiskEngine sizing limits (capped at 8)."""
        sig = Signal(
            signal_id="SIG-SEC-01",
            strategy_id="ATTACKER_STRAT",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=1.0,
            timestamp=self.now,
            expiry=self.now,
            source="ExternalSignal"
        )

        dec = self.engine.evaluate_order_request(
            signal=sig,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10000,
            context=self.context,
            limits=self.limits
        )

        # RiskEngine caps quantity at 8 (2C symbol cap ₹20,000 / ₹2,500)
        self.assertEqual(dec.approved_quantity, 8)
        self.assertTrue(ExecutionAuthorizationGate.can_execute(dec))
        self.assertLess(dec.approved_quantity, 10000)

    def test_active_kill_switch_cannot_be_bypassed_by_confidence_or_strategy(self):
        """High confidence (1.0) or fake strategy ID cannot bypass global kill switch."""
        self.kill_switch.trigger_global(reason="Security Lockdown")

        sig = Signal(
            signal_id="SIG-SEC-02",
            strategy_id="ADMIN_OVERRIDE_ATTEMPT",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,
            target_price=2600.0,
            confidence=1.0,
            timestamp=self.now,
            expiry=self.now,
            source="ExternalSignal"
        )

        dec = self.engine.evaluate_order_request(
            signal=sig,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )

        self.assertEqual(dec.decision, RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertFalse(ExecutionAuthorizationGate.can_execute(dec))

    def test_forged_risk_decision_object_rejected_by_execution_gate(self):
        """Caller attempting to forge a RiskDecision with status=APPROVED and quantity=99999 is blocked unless valid."""
        # Case A: Forged dictionary object
        forged_dict = {
            "decision_id": "RD-FORGED",
            "decision": "APPROVED",
            "approved_quantity": 999999
        }
        self.assertFalse(ExecutionAuthorizationGate.can_execute(forged_dict))

        # Case B: Forged RiskDecision with invalid zero quantity
        forged_zero_qty = RiskDecision(
            decision_id="RD-FORGED-02",
            signal_id="SIG-01",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=0,
            timestamp=self.now
        )
        self.assertFalse(ExecutionAuthorizationGate.can_execute(forged_zero_qty))


if __name__ == "__main__":
    unittest.main()
