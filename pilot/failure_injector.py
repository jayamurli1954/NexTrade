# pilot/failure_injector.py
"""
Failure Injection & Recovery Drills Harness for NexTrade (Sub-Phase 4K).
Simulates real-world failure conditions (network timeouts, partial fills, broker disconnects,
process crashes) in safe isolated environments (Invariant 4K-P8).
"""
import random
from typing import Dict, Any, Tuple, Optional

from contracts.safety_contracts import ExecutionEnvironment


class FailureInjector:
    """
    Simulates operational fault scenarios under strict simulation/paper isolation.
    """

    def __init__(self, environment: ExecutionEnvironment = ExecutionEnvironment.PAPER):
        self.environment = environment
        self._active_fault: Optional[str] = None

    def inject_fault(self, fault_type: str, environment: ExecutionEnvironment) -> Tuple[bool, str]:
        """
        Injects a failure scenario ONLY if environment is PAPER or SANDBOX (Invariant 4K-P8).
        """
        if environment == ExecutionEnvironment.LIVE:
            return False, "INJECTION_DENIED: Fault injection is strictly forbidden in LIVE environment (Invariant 4K-P8)"

        self._active_fault = fault_type
        return True, f"FAULT_INJECTED: Active fault '{fault_type}' armed for environment {environment.value}"

    def evaluate_simulated_dispatch(self, order_id: str) -> Dict[str, Any]:
        """
        Evaluates simulated dispatch response based on active fault.
        """
        if self._active_fault == "NETWORK_TIMEOUT":
            return {"status": "UNKNOWN", "reason": "SIMULATED_NETWORK_TIMEOUT", "reconciliation_required": True}
        if self._active_fault == "PARTIAL_FILL":
            return {"status": "PARTIAL_FILL", "filled_quantity": 1.0, "remaining_quantity": 4.0}
        if self._active_fault == "BROKER_DISCONNECT":
            return {"status": "DISCONNECTED", "reason": "SIMULATED_BROKER_DISCONNECT", "reconciliation_required": True}
        if self._active_fault == "DUPLICATE_EVENT":
            return {"status": "DUPLICATE", "reason": "SIMULATED_DUPLICATE_EVENT"}

        return {"status": "NORMAL", "reason": "NO_FAULT"}

    def clear_faults(self) -> None:
        """Clears active fault state."""
        self._active_fault = None
