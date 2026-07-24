# tests/test_kill_switch.py
"""
Unit Test Suite for NexTrade Phase 2D Multi-Level Kill Switch & Circuit Breakers Engine.
Tests scope isolation, precedence hierarchy, atomic persistence, fail-closed recovery,
audit metadata tracking, and thread-safety concurrency.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta

from decimal import Decimal

from contracts.order import OrderSide
from contracts.risk import OrderIntent
from risk.kill_switch import (
    KillSwitchManager,
    KillSwitchLevel,
    CircuitBreakerType,
    KillSwitchCheckResult,
    SCHEMA_VERSION,
)


class TestKillSwitchManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "kill_switch_state.json")
        self.manager = KillSwitchManager(state_file_path=self.state_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_global_kill_switch_blocks_entry(self):
        self.manager.trigger_global(reason="Emergency Stop")
        res = self.manager.evaluate_kill_switch(
            strategy_id="TREND_01",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=100
        )
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.authorized_quantity, 0)
        self.assertEqual(res.blocking_level, KillSwitchLevel.GLOBAL)

    def test_global_kill_switch_permits_exit(self):
        self.manager.trigger_global(reason="Emergency Stop")
        res = self.manager.evaluate_kill_switch(
            strategy_id="TREND_01",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.EXIT,
            candidate_quantity=100
        )
        self.assertFalse(res.is_blocked)
        self.assertEqual(res.authorized_quantity, 100)

    def test_broker_offline_blocks_exit(self):
        self.manager.set_broker_health("ANGEL_ONE", is_available=False)
        res = self.manager.evaluate_kill_switch(
            strategy_id="TREND_01",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.EXIT,
            candidate_quantity=100
        )
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.authorized_quantity, 0)
        self.assertEqual(res.blocking_level, KillSwitchLevel.BROKER)

    def test_strategy_scope_isolation(self):
        self.manager.trigger_strategy(strategy_id="STRAT_A", reason="Strategy Bug")
        res_a = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res_a.is_blocked)
        self.assertEqual(res_a.blocking_level, KillSwitchLevel.STRATEGY)

        res_b = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_B",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertFalse(res_b.is_blocked)
        self.assertEqual(res_b.authorized_quantity, 50)

    def test_symbol_scope_isolation(self):
        self.manager.trigger_symbol(symbol="RELIANCE", reason="Corporate Action Pending")
        res_rel = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res_rel.is_blocked)
        self.assertEqual(res_rel.blocking_level, KillSwitchLevel.SYMBOL)

        res_tcs = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="TCS",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertFalse(res_tcs.is_blocked)

    def test_broker_scope_isolation(self):
        self.manager.trigger_broker(broker_name="ANGEL_ONE", reason="High Latency")
        res_angel = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res_angel.is_blocked)
        self.assertEqual(res_angel.blocking_level, KillSwitchLevel.BROKER)

        res_paper = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="PAPER_BROKER",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertFalse(res_paper.is_blocked)

    def test_precedence_hierarchy_resolution(self):
        # Trigger Global, Strategy, and Symbol simultaneously
        self.manager.trigger_global(reason="Global Halt")
        self.manager.trigger_strategy(strategy_id="STRAT_A", reason="Strategy Halt")
        self.manager.trigger_symbol(symbol="RELIANCE", reason="Symbol Halt")

        res = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res.is_blocked)
        # Highest priority Global must be returned
        self.assertEqual(res.blocking_level, KillSwitchLevel.GLOBAL)

    def test_circuit_breaker_triggers(self):
        self.manager.trigger_circuit_breaker(CircuitBreakerType.DAILY_LOSS, reason="Daily loss breached")
        res = self.manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.breaker_type, CircuitBreakerType.DAILY_LOSS)

    def test_atomic_persistence_and_recovery(self):
        self.manager.trigger_strategy(strategy_id="STRAT_A", reason="Test Persistence")
        self.assertTrue(os.path.exists(self.state_file))

        # Re-initialize manager from state file
        new_manager = KillSwitchManager(state_file_path=self.state_file)
        res = new_manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.blocking_level, KillSwitchLevel.STRATEGY)

    def test_fail_closed_on_corrupt_state_file(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write("{ INVALID_JSON_CONTENT ...")

        corrupt_manager = KillSwitchManager(state_file_path=self.state_file)
        res = corrupt_manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.blocking_level, KillSwitchLevel.GLOBAL)
        self.assertIn("STATE_PERSISTENCE_FAILURE", res.reason)

    def test_fail_closed_on_unsupported_schema_version(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 999, "global_active": False}, f)

        bad_schema_manager = KillSwitchManager(state_file_path=self.state_file)
        res = bad_schema_manager.evaluate_kill_switch(
            strategy_id="STRAT_A",
            symbol="RELIANCE",
            broker_name="ANGEL_ONE",
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=50
        )
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.blocking_level, KillSwitchLevel.GLOBAL)
        self.assertIn("STATE_PERSISTENCE_FAILURE", res.reason)

    def test_audit_metadata_tracking(self):
        self.manager.trigger_global(reason="Audit Test", source="OPERATOR_CLI")
        self.assertIsNotNone(self.manager._global_audit)
        self.assertEqual(self.manager._global_audit.trigger_reason, "Audit Test")
        self.assertEqual(self.manager._global_audit.trigger_source, "OPERATOR_CLI")

        self.manager.reset_global(reason="Audit Clear", source="OPERATOR_CLI")
        self.assertFalse(self.manager._global_active)
        self.assertEqual(self.manager._global_audit.reset_reason, "Audit Clear")

    def test_thread_safety_concurrency(self):
        def worker(mgr, i):
            mgr.trigger_symbol(symbol=f"SYM_{i}", reason=f"Thread {i}")
            mgr.evaluate_kill_switch("STRAT", f"SYM_{i}", "ANGEL_ONE", OrderIntent.ENTRY, 10)

        threads = [threading.Thread(target=worker, args=(self.manager, i)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        res = self.manager.evaluate_kill_switch("STRAT", "SYM_5", "ANGEL_ONE", OrderIntent.ENTRY, 10)
        self.assertTrue(res.is_blocked)

    def test_stale_data_feed_threshold_evaluation(self):
        mgr = KillSwitchManager(
            state_file_path=self.state_file,
            stale_data_thresholds={
                ("NSE", "1m"): Decimal("30.0"),
                ("NSE", "5m"): Decimal("90.0"),
            }
        )
        now = datetime.now(timezone.utc)
        # 29 seconds old -> Fresh
        self.assertFalse(mgr.check_stale_data("NSE", "1m", now - timedelta(seconds=29), now=now))

        # 30 seconds old -> Stale (Trips breaker)
        self.assertTrue(mgr.check_stale_data("NSE", "1m", now - timedelta(seconds=30), now=now))
        res = mgr.evaluate_kill_switch("STRAT", "RELIANCE", "ANGEL_ONE", OrderIntent.ENTRY, 50)
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.breaker_type, CircuitBreakerType.STALE_DATA)

    def test_stale_data_vs_daily_loss_precedence(self):
        # Trigger STALE_DATA (Priority 6) and DAILY_LOSS (Priority 7)
        self.manager.trigger_circuit_breaker(CircuitBreakerType.DAILY_LOSS, reason="Daily loss breached")
        self.manager.trigger_circuit_breaker(CircuitBreakerType.STALE_DATA, reason="Feed stale")

        res = self.manager.evaluate_kill_switch("STRAT", "RELIANCE", "ANGEL_ONE", OrderIntent.ENTRY, 50)
        self.assertTrue(res.is_blocked)
        self.assertEqual(res.breaker_type, CircuitBreakerType.STALE_DATA)

    def test_quantity_invariant_bounds(self):
        # Unblocked ENTRY
        res_unblocked = self.manager.evaluate_kill_switch("STRAT", "RELIANCE", "ANGEL_ONE", OrderIntent.ENTRY, 100)
        self.assertFalse(res_unblocked.is_blocked)
        self.assertEqual(res_unblocked.authorized_quantity, 100)

        # Blocked ENTRY
        self.manager.trigger_global("Block")
        res_blocked = self.manager.evaluate_kill_switch("STRAT", "RELIANCE", "ANGEL_ONE", OrderIntent.ENTRY, 100)
        self.assertTrue(res_blocked.is_blocked)
        self.assertEqual(res_blocked.authorized_quantity, 0)

        # Blocked EXIT by risk policy (allowed by risk policy)
        res_exit = self.manager.evaluate_kill_switch("STRAT", "RELIANCE", "ANGEL_ONE", OrderIntent.EXIT, 100)
        self.assertFalse(res_exit.is_blocked)
        self.assertEqual(res_exit.authorized_quantity, 100)

        # Blocked EXIT by broker offline
        self.manager.set_broker_health("ANGEL_ONE", is_available=False)
        res_broker_off = self.manager.evaluate_kill_switch("STRAT", "RELIANCE", "ANGEL_ONE", OrderIntent.EXIT, 100)
        self.assertTrue(res_broker_off.is_blocked)
        self.assertEqual(res_broker_off.authorized_quantity, 0)

    def test_individual_reset_isolation(self):
        self.manager.trigger_global("Global")
        self.manager.trigger_strategy("STRAT_A", "Strategy A")

        # Reset Global does NOT clear Strategy A
        self.manager.reset_global("Reset Global")
        res_a = self.manager.evaluate_kill_switch("STRAT_A", "RELIANCE", "ANGEL_ONE", OrderIntent.ENTRY, 50)
        self.assertTrue(res_a.is_blocked)
        self.assertEqual(res_a.blocking_level, KillSwitchLevel.STRATEGY)

        # Reset Strategy A clears Strategy A
        self.manager.reset_strategy("STRAT_A", "Reset Strategy A")
        res_a_cleared = self.manager.evaluate_kill_switch("STRAT_A", "RELIANCE", "ANGEL_ONE", OrderIntent.ENTRY, 50)
        self.assertFalse(res_a_cleared.is_blocked)


if __name__ == "__main__":
    unittest.main()

