# tests/test_protection_contracts.py
"""
Unit Test Suite for NexTrade Protection & Exit Management Contracts.
Verifies Invariants E17 - E23:
E17 (Stop-Loss Integrity): LONG SL < Entry, SHORT SL > Entry.
E18 (Target Integrity): LONG TP > Entry, SHORT TP < Entry.
E19 (Trailing Monotonicity): LONG SL new >= prev, SHORT SL new <= prev.
E20 (Trailing Step Integrity): Trailing update occurs ONLY IF market movement >= trailing_step relative to last_reference_price.
E21 (No Protection Weakening): Active SL cannot move in unfavorable risk direction.
E23 (Protection Auditability): ProtectionAdjustmentEvent immutability and lineage traceability.
Also tests TrailingDistanceType (ABSOLUTE vs PERCENTAGE) and ProtectionDecision.
"""
import unittest
from datetime import datetime, timezone

from contracts.position import PositionSide
from contracts.protection import (
    ProtectionPlan,
    TrailingDistanceType,
    TrailingStopState,
    ProtectionDecision,
    ProtectionDecisionType,
    ProtectionAdjustmentEvent,
)


class TestProtectionContracts(unittest.TestCase):

    def test_valid_long_protection_plan_absolute_and_percentage(self):
        plan_abs = ProtectionPlan(
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            initial_stop_loss=2450.0,
            initial_take_profit=2600.0,
            trailing_enabled=True,
            trailing_distance=20.0,
            trailing_distance_type=TrailingDistanceType.ABSOLUTE,
            trailing_step=10.0
        )
        self.assertEqual(plan_abs.entry_price, 2500.0)
        self.assertEqual(plan_abs.trailing_distance_type, TrailingDistanceType.ABSOLUTE)

        plan_pct = ProtectionPlan(
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            initial_stop_loss=2450.0,
            initial_take_profit=2600.0,
            trailing_enabled=True,
            trailing_distance=2.0,  # 2.0%
            trailing_distance_type=TrailingDistanceType.PERCENTAGE,
            trailing_step=10.0
        )
        self.assertEqual(plan_pct.trailing_distance_type, TrailingDistanceType.PERCENTAGE)

    def test_invariant_e17_long_stop_loss_breach_raises_error(self):
        """Invariant E17: LONG SL >= Entry Price MUST raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            ProtectionPlan(
                position_side=PositionSide.LONG,
                entry_price=2500.0,
                initial_stop_loss=2550.0,  # Invalid for LONG
                initial_take_profit=2600.0
            )
        self.assertIn("Invariant E17 Breached (LONG)", str(ctx.exception))

    def test_invariant_e17_short_stop_loss_breach_raises_error(self):
        """Invariant E17: SHORT SL <= Entry Price MUST raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            ProtectionPlan(
                position_side=PositionSide.SHORT,
                entry_price=2500.0,
                initial_stop_loss=2450.0,  # Invalid for SHORT
                initial_take_profit=2400.0
            )
        self.assertIn("Invariant E17 Breached (SHORT)", str(ctx.exception))

    def test_invariant_e18_long_target_breach_raises_error(self):
        """Invariant E18: LONG TP <= Entry Price MUST raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            ProtectionPlan(
                position_side=PositionSide.LONG,
                entry_price=2500.0,
                initial_stop_loss=2450.0,
                initial_take_profit=2400.0  # Invalid for LONG
            )
        self.assertIn("Invariant E18 Breached (LONG)", str(ctx.exception))

    def test_invariant_e18_short_target_breach_raises_error(self):
        """Invariant E18: SHORT TP >= Entry Price MUST raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            ProtectionPlan(
                position_side=PositionSide.SHORT,
                entry_price=2500.0,
                initial_stop_loss=2550.0,
                initial_take_profit=2600.0  # Invalid for SHORT
            )
        self.assertIn("Invariant E18 Breached (SHORT)", str(ctx.exception))

    def test_long_trailing_stop_progression_and_step_integrity(self):
        """
        Tests LONG Trailing Stop Progression (Invariants E19 & E20):
        Entry: 2500, Initial SL: 2450, Distance: 20, Step: 10
        Price 2510 -> Delta 10 >= Step 10 -> SL moves to 2510 - 20 = 2490
        Price 2515 -> Delta 5 < Step 10 (relative to 2510) -> No movement
        Price 2530 -> Delta 20 >= Step 10 (relative to 2510) -> SL moves to 2530 - 20 = 2510
        Price 2500 (reversal) -> SL NEVER decreases (Monotonicity E19 & E21) -> Remains 2510
        """
        state = TrailingStopState(
            position_side=PositionSide.LONG,
            entry_price=2500.0,
            current_stop_loss=2450.0,
            trailing_distance=20.0,
            trailing_distance_type=TrailingDistanceType.ABSOLUTE,
            trailing_step=10.0,
            highest_favorable_price=2500.0,
            last_reference_price=2500.0
        )

        # 1. Price moves to 2510 (Delta 10 >= Step 10) -> Updates SL to 2490
        upd, state = state.calculate_update(2510.0)
        self.assertTrue(upd)
        self.assertEqual(state.current_stop_loss, 2490.0)
        self.assertEqual(state.last_reference_price, 2510.0)

        # 2. Price moves to 2515 (Delta 5 < Step 10 relative to last_reference_price 2510) -> No update
        upd, state = state.calculate_update(2515.0)
        self.assertFalse(upd)
        self.assertEqual(state.current_stop_loss, 2490.0)

        # 3. Price moves to 2530 (Delta 20 >= Step 10 relative to 2510) -> Updates SL to 2510
        upd, state = state.calculate_update(2530.0)
        self.assertTrue(upd)
        self.assertEqual(state.current_stop_loss, 2510.0)
        self.assertEqual(state.last_reference_price, 2530.0)

        # 4. Market reverses to 2500 -> Monotonicity check (SL MUST NOT decrease below 2510)
        upd, state = state.calculate_update(2500.0)
        self.assertFalse(upd)
        self.assertEqual(state.current_stop_loss, 2510.0)

    def test_short_trailing_stop_progression_and_step_integrity(self):
        """
        Tests SHORT Trailing Stop Progression (Invariants E19 & E20):
        Entry: 2500, Initial SL: 2550, Distance: 20, Step: 10
        Price 2490 -> Delta 10 >= Step 10 -> SL moves to 2490 + 20 = 2510
        Price 2485 -> Delta 5 < Step 10 -> No movement
        Price 2470 -> Delta 20 >= Step 10 -> SL moves to 2470 + 20 = 2490
        Price 2520 (reversal) -> SL NEVER increases (Monotonicity E19 & E21) -> Remains 2490
        """
        state = TrailingStopState(
            position_side=PositionSide.SHORT,
            entry_price=2500.0,
            current_stop_loss=2550.0,
            trailing_distance=20.0,
            trailing_distance_type=TrailingDistanceType.ABSOLUTE,
            trailing_step=10.0,
            highest_favorable_price=2500.0,
            last_reference_price=2500.0
        )

        # 1. Price drops to 2490 (Delta 10 >= Step 10) -> Updates SL down to 2510
        upd, state = state.calculate_update(2490.0)
        self.assertTrue(upd)
        self.assertEqual(state.current_stop_loss, 2510.0)
        self.assertEqual(state.last_reference_price, 2490.0)

        # 2. Price drops to 2485 (Delta 5 < Step 10) -> No update
        upd, state = state.calculate_update(2485.0)
        self.assertFalse(upd)
        self.assertEqual(state.current_stop_loss, 2510.0)

        # 3. Price drops to 2470 (Delta 20 >= Step 10) -> Updates SL down to 2490
        upd, state = state.calculate_update(2470.0)
        self.assertTrue(upd)
        self.assertEqual(state.current_stop_loss, 2490.0)
        self.assertEqual(state.last_reference_price, 2470.0)

        # 4. Market reverses up to 2520 -> Monotonicity check (SHORT SL MUST NOT increase above 2490)
        upd, state = state.calculate_update(2520.0)
        self.assertFalse(upd)
        self.assertEqual(state.current_stop_loss, 2490.0)

    def test_protection_decision_contract(self):
        """Tests ProtectionDecision creation and fields."""
        dec = ProtectionDecision(
            decision=ProtectionDecisionType.UPDATE_TRAILING_STOP,
            position_id="POS-RELIANCE",
            symbol="RELIANCE",
            position_side=PositionSide.LONG,
            trigger_price=2530.0,
            current_stop_loss=2490.0,
            new_stop_loss=2510.0,
            reason="Trailing step reached"
        )
        self.assertEqual(dec.decision, ProtectionDecisionType.UPDATE_TRAILING_STOP)
        self.assertEqual(dec.new_stop_loss, 2510.0)

    def test_protection_adjustment_event_traceability(self):
        """Invariant E23: ProtectionAdjustmentEvent traceability."""
        evt = ProtectionAdjustmentEvent(
            event_id="PAE-01",
            execution_request_id="EXREQ-01",
            risk_decision_id="RD-01",
            symbol="RELIANCE",
            position_side=PositionSide.LONG,
            previous_stop_loss=2450.0,
            new_stop_loss=2490.0,
            trigger_market_price=2510.0,
            reason="TRAILING_STEP_TRIGGER"
        )
        self.assertEqual(evt.previous_stop_loss, 2450.0)
        self.assertEqual(evt.new_stop_loss, 2490.0)
        self.assertEqual(evt.to_dict()["reason"], "TRAILING_STEP_TRIGGER")


if __name__ == "__main__":
    unittest.main()
