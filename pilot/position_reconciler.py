# pilot/position_reconciler.py
"""
Live Position Reconciler & Truth Manager for NexTrade (Sub-Phase 4K).
Compares internal application position state against authoritative broker position truth.
Enforces instant RECONCILIATION_LOCK on position mismatch (Invariant 4K-P7).
"""
import threading
from typing import Dict, Any, Tuple, Optional


class PositionReconciler:
    """
    Thread-safe position reconciler enforcing position truth authority over application state.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._reconciliation_locked = False
        self._discrepancies: Dict[str, Any] = {}

    @property
    def is_locked(self) -> bool:
        with self._lock:
            return self._reconciliation_locked

    def reconcile_positions(
        self,
        internal_positions: Dict[str, float],
        broker_positions: Dict[str, float]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Reconciles internal position quantities against authoritative broker position truth.
        If any symbol quantity differs -> triggers RECONCILIATION_LOCK.
        """
        with self._lock:
            all_symbols = set(internal_positions.keys()).union(set(broker_positions.keys()))
            mismatches = {}

            for sym in all_symbols:
                int_qty = internal_positions.get(sym, 0.0)
                brk_qty = broker_positions.get(sym, 0.0)
                if abs(int_qty - brk_qty) > 1e-5:
                    mismatches[sym] = {
                        "internal_quantity": int_qty,
                        "broker_quantity": brk_qty,
                        "delta": brk_qty - int_qty
                    }

            if mismatches:
                self._reconciliation_locked = True
                self._discrepancies = mismatches
                reason = f"RECONCILIATION_LOCK_ACTIVATED: Position mismatch detected on symbols {list(mismatches.keys())}"
                return False, reason, mismatches

            self._reconciliation_locked = False
            self._discrepancies = {}
            return True, "RECONCILIATION_CLEAN: Internal positions match broker position truth", {}

    def can_dispatch_order(self, symbol: str) -> Tuple[bool, str]:
        """
        Evaluates whether order dispatch is permitted under position reconciliation state.
        If locked -> DENIES all new orders (Invariant 4K-P7).
        """
        with self._lock:
            if self._reconciliation_locked:
                return False, f"DISPATCH_DENIED: PositionReconciler is locked due to active discrepancies ({self._discrepancies})"
            return True, "AUTHORIZED: Position reconciliation clean"

    def reset_reconciliation_lock(self, operator_recovery_id: str) -> Tuple[bool, str]:
        """Unlocks reconciliation state only with explicit operator recovery ID."""
        with self._lock:
            if not operator_recovery_id:
                return False, "UNLOCK_DENIED: Explicit operator recovery ID required"
            self._reconciliation_locked = False
            self._discrepancies = {}
            return True, f"RECONCILIATION_UNLOCKED: Lock cleared by operator {operator_recovery_id}"
