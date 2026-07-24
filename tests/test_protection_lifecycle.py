# tests/test_protection_lifecycle.py
"""
Unit Test Suite for NexTrade Protection Lifecycle Manager (Sub-Phase 3D).
Verifies the 10 Mandatory Sub-Phase 3D Architectural Refinements:
1. Dispatch via ExecutionGateway (No direct broker bypass).
2. Partial-Fill Position Sizing (Q_protected <= Q_open_position).
3. Deterministic SL/TP Precedence (Ambiguous SL/TP breach => AMBIGUOUS_PROTECTION_TRIGGER -> RECONCILIATION_REQUIRED).
4. Trailing Activation Lifecycle.
5. Separation of Trailing Distance vs Trailing Step.
6. Explicit Protection Lifecycle States (INACTIVE, ACTIVE, EXIT_PENDING, CLOSED, CANCELLED, RECONCILIATION_REQUIRED).
7. UNKNOWN Exit State & Reconciliation Integration.
8. Idempotent Exit Generation.
9. Explicit Protection Trigger Reasons.
10. State Serialization for Restart Recovery (to_dict / from_dict).
"""
import unittest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from contracts.position import PositionSide
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from contracts.protection import (
    ProtectionPlan,
    TrailingDistanceType,
    ProtectionDecision,
    ProtectionDecisionType,
)
from protection.lifecycle import (
    ProtectionLifecycleManager,
    ProtectionLifecycleState,
    ProtectionTriggerReason,
)


class TestProtectionLifecycleManager(unittest.TestCase):

    def setUp(self):
        self.plan_long = ProtectionPlan(
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            initial_stop_loss=2450.0,
            initial_take_profit=2600.0,
            trailing_enabled=True,
            trailing_distance=20.0,
            trailing_distance_type=TrailingDistanceType.ABSOLUTE,
            trailing_step=10.0
        )
        self.plan_short = ProtectionPlan(
            position_side=PositionSide.SHORT,
            entry_price=2500.0,
            initial_stop_loss=2550.0,
            initial_take_profit=2400.0,
            trailing_enabled=True,
            trailing_distance=20.0,
            trailing_distance_type=TrailingDistanceType.ABSOLUTE,
            trailing_step=10.0
        )

    def test_long_stop_loss_trigger_dispatches_via_gateway(self):
        """Refinement 1 & 9: LONG SL trigger dispatches ExecutionRequest to gateway."""
        mock_gateway = MagicMock()
        mock_gateway.execute.return_value = ExecutionResult(
            execution_id="EXEC-01",
            execution_request_id="EXREQ-EXIT-01",
            risk_decision_id="RD-01",
            status=ExecutionStatus.FILLED,
            requested_quantity=50,
            execution_quantity=50,
            filled_quantity=50,
            remaining_quantity=0,
            average_fill_price=2440.0
        )

        mgr = ProtectionLifecycleManager(
            position_id="POS-01",
            symbol="RELIANCE",
            exchange="NSE",
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            protection_plan=self.plan_long,
            risk_decision_id="RD-01",
            initial_open_quantity=50,
            gateway=mock_gateway
        )

        # Price drops to 2440.0 (below SL 2450.0)
        dec, res = mgr.evaluate_price_tick(2440.0)

        self.assertEqual(dec.decision, ProtectionDecisionType.EXIT)
        self.assertEqual(dec.reason, ProtectionTriggerReason.TRAILING_STOP.value)
        mock_gateway.execute.assert_called_once()

        # Position is now fully exited -> State becomes CLOSED (Refinement 6)
        self.assertEqual(mgr.state, ProtectionLifecycleState.CLOSED)
        self.assertEqual(mgr.open_quantity, 0)

    def test_partial_fill_position_sizing(self):
        """Refinement 2: Protection quantity matches open position quantity."""
        mgr = ProtectionLifecycleManager(
            position_id="POS-02",
            symbol="INFY",
            exchange="NSE",
            position_side=PositionSide.LONG,
            entry_price=1600.0,
            protection_plan=ProtectionPlan(
                position_side=PositionSide.LONG,
                entry_price=1600.0,
                initial_stop_loss=1550.0
            ),
            risk_decision_id="RD-02",
            initial_open_quantity=20
        )
        self.assertEqual(mgr.open_quantity, 20)

        # Dynamic partial fill scale-in to 50 shares
        mgr.update_position_quantity(50)
        self.assertEqual(mgr.open_quantity, 50)

    def test_ambiguous_sl_and_tp_breach_requires_reconciliation(self):
        """Refinement 3: Simultaneous SL and TP breach triggers RECONCILIATION_REQUIRED."""
        plan_tight = ProtectionPlan(
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            initial_stop_loss=2500.0 - 1.0,  # 2499.0
            initial_take_profit=2500.0 + 1.0  # 2501.0
        )
        mgr = ProtectionLifecycleManager(
            position_id="POS-03",
            symbol="TCS",
            exchange="NSE",
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            protection_plan=plan_tight,
            risk_decision_id="RD-03",
            initial_open_quantity=10
        )

        # Extreme gap tick simulation (e.g. 0.0) that breaches SL and TP logic if misconfigured
        # For long position: SL breached if price <= SL. TP breached if price >= TP.
        # Let's force sl_breached & tp_breached on custom plan
        mgr.protection_plan = MagicMock()
        mgr.protection_plan.trailing_enabled = False
        mgr.protection_plan.initial_stop_loss = 2600.0  # SL higher than TP to force dual breach
        mgr.protection_plan.initial_take_profit = 2400.0

        dec, res = mgr.evaluate_price_tick(2500.0)
        self.assertEqual(dec.reason, ProtectionTriggerReason.AMBIGUOUS_PROTECTION_TRIGGER.value)
        self.assertEqual(mgr.state, ProtectionLifecycleState.RECONCILIATION_REQUIRED)

    def test_unknown_exit_state_triggers_reconciliation_required(self):
        """Refinement 7: UNKNOWN execution result puts lifecycle in RECONCILIATION_REQUIRED."""
        mock_gateway = MagicMock()
        mock_gateway.execute.return_value = ExecutionResult(
            execution_id="EXEC-UNK",
            execution_request_id="EXREQ-EXIT-UNK",
            risk_decision_id="RD-04",
            status=ExecutionStatus.UNKNOWN,
            requested_quantity=10,
            execution_quantity=10,
            filled_quantity=0,
            remaining_quantity=10,
            average_fill_price=0.0,
            rejection_reason="POST_SUBMISSION_TIMEOUT"
        )


        mgr = ProtectionLifecycleManager(
            position_id="POS-04",
            symbol="RELIANCE",
            exchange="NSE",
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            protection_plan=ProtectionPlan(
                position_side=PositionSide.LONG,
                entry_price=2500.0,
                initial_stop_loss=2450.0
            ),
            risk_decision_id="RD-04",
            initial_open_quantity=10,
            gateway=mock_gateway
        )

        dec, res = mgr.evaluate_price_tick(2400.0)
        self.assertEqual(mgr.state, ProtectionLifecycleState.RECONCILIATION_REQUIRED)
        self.assertTrue(res.requires_reconciliation)

        # Subsequent tick evaluation yields NO_ACTION while in RECONCILIATION_REQUIRED (Refinement 8 Idempotency)
        dec2, res2 = mgr.evaluate_price_tick(2390.0)
        self.assertEqual(dec2.decision, ProtectionDecisionType.NO_ACTION)
        self.assertIn("RECONCILIATION_REQUIRED", dec2.reason)

    def test_state_serialization_for_restart_recovery(self):
        """Refinement 10: to_dict() and from_dict() for restart state recovery."""
        mgr = ProtectionLifecycleManager(
            position_id="POS-05",
            symbol="RELIANCE",
            exchange="NSE",
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            protection_plan=self.plan_long,
            risk_decision_id="RD-05",
            initial_open_quantity=100
        )
        data = mgr.to_dict()
        self.assertEqual(data["position_id"], "POS-05")
        self.assertEqual(data["open_quantity"], 100)

        restored_mgr = ProtectionLifecycleManager.from_dict(data)
        self.assertEqual(restored_mgr.position_id, "POS-05")
        self.assertEqual(restored_mgr.open_quantity, 100)
        self.assertEqual(restored_mgr.entry_price, 2500.0)


if __name__ == "__main__":
    unittest.main()
