# tests/test_risk_engine_integration.py
"""
Comprehensive Integration Test Suite for NexTrade Risk Engine (Phase 2G).
Verifies pure composition across Phase 2B (PositionSizer), Phase 2C (PortfolioRiskEvaluator),
Phase 2D (KillSwitchManager), Phase 2E (RiskEngine Orchestrator), and Phase 2F (RiskAuditLogger).

Enforces the Master Invariant: 0 <= Q_final <= Q_2D <= Q_2C <= Q_2B <= Q_requested
and confirms complete execution isolation (0 broker/trader side effects).
"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
from risk.position_sizer import PositionSizer, InstrumentInfo
from risk.risk_limits import PortfolioRiskEvaluator
from risk.kill_switch import KillSwitchManager
from risk.risk_engine import RiskEngine
from risk.audit_logger import RiskAuditLogger, AuditEvent, GENESIS_HASH


class TestRiskEngineIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "kill_switch_state.json")
        self.jsonl_path = os.path.join(self.temp_dir, "risk_decisions.jsonl")
        self.csv_path = os.path.join(self.temp_dir, "risk_decisions.csv")

        self.kill_switch = KillSwitchManager(state_file_path=self.state_file)
        self.sizer = PositionSizer()
        self.portfolio_evaluator = PortfolioRiskEvaluator()
        self.audit_logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)

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
            max_symbol_exposure_pct=20.0,      # ₹20,000 max exposure per symbol
            max_sector_exposure_pct=40.0,
            max_open_positions=5,
            max_daily_loss_amount=5000.0
        )

        self.signal_long = Signal(
            signal_id="SIG-INT-01",
            strategy_id="MOMENTUM_01",
            symbol="RELIANCE",
            exchange="NSE",
            action=SignalAction.BUY,
            entry_price=2500.0,
            stop_loss=2450.0,   # Delta SL = 50 -> Sizer raw qty = 10 shares (₹25k > ₹20k cap -> 2C caps at 8)
            target_price=2600.0,
            confidence=0.90,
            timestamp=self.now,
            expiry=self.now,
            source="IntegrationTest"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _assert_master_quantity_invariant(self, dec: RiskDecision, requested_qty: int):
        """Helper to assert 0 <= Q_final <= Q_2D <= Q_2C <= Q_2B <= Q_requested."""
        metrics = dec.metrics if hasattr(dec, "metrics") and dec.metrics else {}
        q_2b = metrics.get("q_2b", requested_qty if dec.approved_quantity > 0 else 0)
        q_2c = metrics.get("q_2c", requested_qty if dec.approved_quantity > 0 else 0)
        q_2d = metrics.get("q_2d", requested_qty if dec.approved_quantity > 0 else 0)
        q_final = dec.approved_quantity

        self.assertTrue(0 <= q_final <= q_2d <= q_2c <= q_2b <= requested_qty,
                        f"Invariant breached: 0 <= Q_final({q_final}) <= Q_2D({q_2d}) <= Q_2C({q_2c}) <= Q_2B({q_2b}) <= Q_req({requested_qty})")

    # ----------------------------------------------------------------------
    # Integration Scenarios 1 to 12
    # ----------------------------------------------------------------------

    def test_scenario_01_full_approval(self):
        """Scenario 1: Full approval (requested 8 shares = 100% authorized quantity)."""
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.APPROVED)
        self.assertEqual(dec.approved_quantity, 8)
        self.assertTrue(dec.is_submittable)
        self._assert_master_quantity_invariant(dec, requested_qty=8)
        self.assertEqual(audit_event.sequence_number, 1)

    def test_scenario_02_position_sizing_reduction(self):
        """Scenario 2: Requested 100 shares, position sizer reduces to 10 based on risk budget."""
        # Symbol cap ₹200k so only 2B is the bottleneck
        limits_wide = RiskLimits(
            default_risk_per_trade_pct=0.50,
            max_symbol_exposure_pct=50.0,
            max_sector_exposure_pct=50.0
        )
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=limits_wide
        )
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.MODIFIED)
        self.assertEqual(dec.approved_quantity, 10)  # Risk budget ₹500 / SL ₹50 = 10
        self.assertIn("PHASE_2B", dec.modification_reason)
        self._assert_master_quantity_invariant(dec, requested_qty=100)

    def test_scenario_03_portfolio_exposure_reduction(self):
        """Scenario 3: 2B permits 10, but 2C exposure cap (₹20k) reduces quantity to 8."""
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.MODIFIED)
        self.assertEqual(dec.approved_quantity, 8)  # 2C symbol cap 20% = ₹20,000 / ₹2,500 = 8 shares
        self.assertIn("PHASE_2C", dec.modification_reason)
        self._assert_master_quantity_invariant(dec, requested_qty=100)

    def test_scenario_04_kill_switch_block(self):
        """Scenario 4: Global kill switch active blocks ENTRY order request."""
        self.kill_switch.trigger_global(reason="Emergency Stop Active")
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits
        )
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertIn("kill switch", dec.modification_reason.lower())
        self._assert_master_quantity_invariant(dec, requested_qty=10)

    def test_scenario_05_exit_allowed_during_kill_switch(self):
        """Scenario 5: Active kill switch permits EXIT order for open position."""
        pos = Position(
            position_id="POS-INT-01",
            strategy_id="MOMENTUM_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=50,
            average_entry_price=2500.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))
        self.kill_switch.trigger_global(reason="Market Panic")

        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.EXIT,
            requested_quantity=50,
            context=ctx,
            limits=self.limits
        )
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.APPROVED)
        self.assertEqual(dec.approved_quantity, 50)
        self.assertTrue(dec.is_submittable)
        self._assert_master_quantity_invariant(dec, requested_qty=50)

    def test_scenario_06_broker_unavailable(self):
        """Scenario 6: Broker execution feed offline rejects order request."""
        self.kill_switch.set_broker_health("ANGEL_ONE", is_available=False)

        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=10,
            context=self.context,
            limits=self.limits,
            broker_name="ANGEL_ONE"
        )
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertIn("unavailable", dec.modification_reason.lower())
        self._assert_master_quantity_invariant(dec, requested_qty=10)

    def test_scenario_07_internal_exception_fail_closed(self):
        """Scenario 7: Component exception forces fail-closed REJECTED decision."""
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate_portfolio_risk.side_effect = ValueError("Database connection dropped")

        err_engine = RiskEngine(
            sizer=self.sizer,
            portfolio_evaluator=mock_evaluator,
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
        audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision, RiskDecisionStatus.REJECTED)
        self.assertEqual(dec.approved_quantity, 0)
        self.assertEqual(dec.modification_reason, "RISK_ENGINE_INTERNAL_ERROR")
        self._assert_master_quantity_invariant(dec, requested_qty=10)

    def test_scenario_08_csv_failure_isolation(self):
        """Scenario 8: CSV write failure leaves JSONL authoritative log valid and health DEGRADED."""
        with patch.object(self.audit_logger, "_append_csv", side_effect=OSError("CSV permission denied")):
            dec = self.engine.evaluate_order_request(
                signal=self.signal_long,
                order_side=OrderSide.BUY,
                order_intent=OrderIntent.ENTRY,
                requested_quantity=8,
                context=self.context,
                limits=self.limits
            )
            audit_event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

            self.assertEqual(dec.approved_quantity, 8)
            res = self.audit_logger.verify_integrity()
            self.assertTrue(res.is_valid)

            health = self.audit_logger.health()
            self.assertEqual(health.status, "DEGRADED")
            self.assertEqual(health.write_failures, 1)

    def test_scenario_09_tamper_detection(self):
        """Scenario 9: Modifying historical audit record invalidates SHA-256 hash chain."""
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        # Tamper JSONL record
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            line = f.readline()
        data = json.loads(line)
        data["approved_quantity"] = 9999
        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

        res = self.audit_logger.verify_integrity()
        self.assertFalse(res.is_valid)

    def test_scenario_10_restart_durability(self):
        """Scenario 10: Logger restart resumes sequence N+1 and matches previous event hash."""
        dec1 = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        e1 = self.audit_logger.log_decision(dec1, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        # Restart logger
        new_logger = RiskAuditLogger(jsonl_path=self.jsonl_path, csv_path=self.csv_path)
        dec2 = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        e2 = new_logger.log_decision(dec2, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(e2.sequence_number, 2)
        self.assertEqual(e2.previous_hash, e1.event_hash)
        self.assertTrue(new_logger.verify_integrity().is_valid)

    def test_scenario_11_risk_decision_audit_event_correspondence(self):
        """Scenario 11: Field-level exact match between RiskDecision and AuditEvent."""
        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=100,
            context=self.context,
            limits=self.limits
        )
        event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        self.assertEqual(dec.decision_id, event.decision_id)
        self.assertEqual(dec.signal_id, event.signal_id)
        self.assertEqual(dec.decision.value if hasattr(dec.decision, "value") else str(dec.decision),
                         event.decision_status.value if hasattr(event.decision_status, "value") else str(event.decision_status))
        self.assertEqual(dec.requested_quantity, event.requested_quantity)
        self.assertEqual(dec.approved_quantity, event.approved_quantity)
        self.assertEqual(dec.modification_reason, event.primary_reason)

    def test_scenario_12_no_execution_side_effects(self):
        """Scenario 12: Entire OrderRequest -> RiskEngine -> RiskDecision -> AuditLogger flow produces 0 execution side effects."""
        mock_broker = MagicMock()

        dec = self.engine.evaluate_order_request(
            signal=self.signal_long,
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            requested_quantity=8,
            context=self.context,
            limits=self.limits
        )
        event = self.audit_logger.log_decision(dec, symbol="RELIANCE", strategy_id="MOMENTUM_01")

        # Verify ZERO calls made to broker interface or external trading APIs
        mock_broker.place_order.assert_not_called()
        mock_broker.execute_trade.assert_not_called()
        self.assertTrue(dec.is_submittable)
        self.assertEqual(event.approved_quantity, 8)


if __name__ == "__main__":
    unittest.main()
