# tests/test_risk_contracts.py
"""
Unit Test Suite for NexTrade Phase 2A Risk Domain Contracts.
Tests enums, immutability, invariants, RiskContext snapshots, and serialization.
"""
import unittest
from datetime import datetime, timezone

from contracts.funds import FundsInfo
from contracts.order import Order, OrderSide, OrderType
from contracts.position import Position, PositionSide
from contracts.risk import (
    OrderIntent,
    RiskDecisionStatus,
    RiskRuleCategory,
    RiskRuleSeverity,
    RiskCheckResult,
    RiskDecision,
    RiskLimits,
    RiskContext,
)


class TestRiskDomainContracts(unittest.TestCase):

    def setUp(self):
        self.funds = FundsInfo(
            available_cash=100000.0,
            used_margin=20000.0,
            available_margin=80000.0,
            total_equity=100000.0
        )
        self.now = datetime.now(timezone.utc)

    def test_order_intent_enum(self):
        self.assertEqual(OrderIntent.ENTRY.value, "ENTRY")
        self.assertEqual(OrderIntent.EXIT.value, "EXIT")
        self.assertEqual(OrderIntent.REDUCE.value, "REDUCE")
        self.assertEqual(OrderIntent.REVERSAL.value, "REVERSAL")

    def test_risk_check_result_immutability(self):
        res = RiskCheckResult(
            rule_name="MaxDailyLossRule",
            category=RiskRuleCategory.DAILY_LOSS,
            passed=True,
            severity=RiskRuleSeverity.BLOCKING,
            reason="Daily loss within limits",
            metrics={"current_loss": 500.0, "limit": 5000.0}
        )
        self.assertEqual(res.rule_name, "MaxDailyLossRule")
        self.assertTrue(res.passed)
        self.assertEqual(res.metrics["current_loss"], 500.0)

        with self.assertRaises((AttributeError, TypeError)):
            res.passed = False

        with self.assertRaises((AttributeError, TypeError)):
            res.metrics["current_loss"] = 1000.0

    def test_risk_limits_default_bounds(self):
        limits = RiskLimits()
        self.assertEqual(limits.min_risk_per_trade_pct, 0.25)
        self.assertEqual(limits.default_risk_per_trade_pct, 0.50)
        self.assertEqual(limits.max_risk_per_trade_pct, 1.00)

        # Test invalid bounds
        with self.assertRaises(ValueError):
            RiskLimits(min_risk_per_trade_pct=1.5, default_risk_per_trade_pct=0.5)

    def test_risk_decision_invariants(self):
        # Approved decision
        dec_approved = RiskDecision(
            decision_id="DEC-001",
            signal_id="SIG-101",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=100,
            approved_quantity=100
        )
        self.assertTrue(dec_approved.is_submittable)

        # Modified decision
        dec_modified = RiskDecision(
            decision_id="DEC-002",
            signal_id="SIG-102",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.MODIFIED,
            requested_quantity=100,
            approved_quantity=60,
            modification_reason="Max single trade exposure cap applied"
        )
        self.assertTrue(dec_modified.is_submittable)
        self.assertEqual(dec_modified.approved_quantity, 60)

        # Rejected decision
        dec_rejected = RiskDecision(
            decision_id="DEC-003",
            signal_id="SIG-103",
            order_intent=OrderIntent.ENTRY,
            decision=RiskDecisionStatus.REJECTED,
            requested_quantity=100,
            approved_quantity=0,
            modification_reason="Daily loss limit breached"
        )
        self.assertFalse(dec_rejected.is_submittable)

        # Invalid invariant: approved > requested
        with self.assertRaises(ValueError):
            RiskDecision(
                decision_id="DEC-999",
                signal_id="SIG-999",
                order_intent=OrderIntent.ENTRY,
                decision=RiskDecisionStatus.APPROVED,
                requested_quantity=50,
                approved_quantity=100
            )

        # Invalid invariant: MODIFIED with approved == 0
        with self.assertRaises(ValueError):
            RiskDecision(
                decision_id="DEC-998",
                signal_id="SIG-998",
                order_intent=OrderIntent.ENTRY,
                decision=RiskDecisionStatus.MODIFIED,
                requested_quantity=100,
                approved_quantity=0
            )

    def test_risk_context_immutability(self):
        pos = Position(
            position_id="POS-01",
            strategy_id="STRAT_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        ctx = RiskContext(
            funds=self.funds,
            open_positions=[pos],
            active_kill_switches={"GLOBAL": False}
        )
        self.assertIsInstance(ctx.open_positions, tuple)
        self.assertEqual(len(ctx.open_positions), 1)

        # Verify context frozen immutability
        with self.assertRaises((AttributeError, TypeError)):
            ctx.daily_realized_pnl = 1000.0

        with self.assertRaises((AttributeError, TypeError)):
            ctx.active_kill_switches["GLOBAL"] = True

    def test_serialization(self):
        res = RiskCheckResult(
            rule_name="KillSwitchRule",
            category=RiskRuleCategory.KILL_SWITCH,
            passed=True,
            severity=RiskRuleSeverity.BLOCKING
        )
        dec = RiskDecision(
            decision_id="DEC-555",
            signal_id="SIG-555",
            order_intent=OrderIntent.EXIT,
            decision=RiskDecisionStatus.APPROVED,
            requested_quantity=50,
            approved_quantity=50,
            checks_evaluated=[res]
        )
        d = dec.to_dict()
        self.assertEqual(d["decision_id"], "DEC-555")
        self.assertEqual(d["order_intent"], "EXIT")

        restored = RiskDecision.from_dict(d)
        self.assertEqual(restored.decision_id, dec.decision_id)
        self.assertEqual(restored.order_intent, OrderIntent.EXIT)
        self.assertEqual(len(restored.checks_evaluated), 1)


if __name__ == "__main__":
    unittest.main()
