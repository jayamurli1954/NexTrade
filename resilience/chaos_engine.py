"""
NexTrade Phase 5H — Resilience Chaos Engine.

Multi-domain adversarial fault injector simulating broker ACK timeouts, clock skew,
Secret Vault locks, and concurrent session_epoch races to test failure containment.
"""

import time
import logging
from typing import Dict, Any, Optional

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from brokers.order_reconciler import OrderReconciler
from governance.secret_vault import SecretVault

logger = logging.getLogger("ResilienceChaosEngine")


class ChaosInjectionException(Exception):
    """Base exception raised during chaos injection testing."""
    pass


class ResilienceChaosEngine:
    """
    Engine injecting multi-domain adversarial faults to verify fail-closed containment.
    """

    def __init__(
        self,
        control_plane: Optional[SafetyControlPlane] = None,
        order_reconciler: Optional[OrderReconciler] = None,
        secret_vault: Optional[SecretVault] = None
    ) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.reconciler = order_reconciler or OrderReconciler(control_plane=self.control_plane)
        self.secret_vault = secret_vault or SecretVault()

    def inject_broker_ack_timeout(self, broker_id: str, order_id: str = "ord_chaos_1") -> None:
        """Injects ACK timeout forcing ORDER_STATE_UNKNOWN and RECONCILIATION_LOCK."""
        logger.warning("CHAOS INJECTION: Simulating ACK timeout for order '%s' on broker '%s'", order_id, broker_id)
        self.reconciler.register_ack_timeout(order_id, f"req_{order_id}")

    def inject_secret_vault_lock(self) -> None:
        """Injects Secret Vault lock simulation."""
        logger.warning("CHAOS INJECTION: Simulating Secret Vault Lock")
        self.control_plane.report_subsystem_state("secret_vault", SafetyState.HARD_HALT, "Secret Vault locked under security compromise")

    def inject_clock_skew(self, skew_seconds: float = 300.0) -> None:
        """Injects clock integrity violation simulation."""
        logger.warning("CHAOS INJECTION: Simulating clock skew of %.1fs", skew_seconds)
        self.control_plane.report_subsystem_state("clock_integrity", SafetyState.HARD_HALT, f"Clock skew of {skew_seconds}s detected")
