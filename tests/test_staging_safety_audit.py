# tests/test_staging_safety_audit.py
"""
Controlled Live Staging Safety Audit Test Suite for NexTrade (Sub-Phase 4J).
Verifies:
1. Invariant 4J-P4: Zero automatic escalation to UNRESTRICTED_LIVE.
2. Invariant 4J-P10: Process restart resets environment to SAFE/DISABLED.
3. Invariant 4J-P11: State uncertainty & network timeout lock dispatches.
4. Invariant 4J-P12: Dominant Emergency Kill Switch forces HARD_HALT.
5. AST Code Scan: Zero unauthorized dispatch or state escalation in staging/ package.
6. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in staging/ package.
"""
import ast
import os
import pytest

from staging.staging_gate import StagingGate
from staging.circuit_breaker import CircuitBreakerManager, CircuitState
from contracts.safety_contracts import ExecutionEnvironment


def test_4j_p4_zero_automatic_escalation_to_unrestricted_live():
    """Verify StagingGate contains zero logic to automatically escalate to UNRESTRICTED_LIVE."""
    gate = StagingGate()
    assert not hasattr(gate, "escalate_to_unrestricted_live")
    assert not hasattr(gate, "enable_unrestricted_live")
    assert gate.environment != ExecutionEnvironment.LIVE


def test_4j_p10_process_restart_resets_environment_to_safe():
    """Verify new process/gate instantiation resets environment to SAFE/PAPER (Invariant 4J-P10)."""
    gate1 = StagingGate()
    assert gate1.environment != ExecutionEnvironment.LIVE

    # Simulate restart
    gate2 = StagingGate()
    assert gate2.environment != ExecutionEnvironment.LIVE


def test_4j_p11_state_uncertainty_forces_reconciliation_lock():
    """Verify state uncertainty or network timeout triggers reconciliation lock (Invariant 4J-P11)."""
    cb = CircuitBreakerManager()
    cb.trigger_reconciliation_lock("NETWORK_TIMEOUT_DETECTED")

    assert cb.current_state == CircuitState.REDUCE_ONLY
    can_exec_inc, _ = cb.can_execute_order(is_risk_reducing=False)
    assert can_exec_inc is False


def test_4j_p12_dominant_kill_switch_forces_hard_halt():
    """Verify emergency kill switch dominates all authorities and forces HARD_HALT (Invariant 4J-P12)."""
    cb = CircuitBreakerManager()
    cb.trigger_kill_switch("EMERGENCY_OPERATOR_HALT")

    assert cb.current_state == CircuitState.HARD_HALT
    can_exec_red, reason_red = cb.can_execute_order(is_risk_reducing=True)
    assert can_exec_red is False
    assert "HARD_HALT" in reason_red


def test_ast_audit_zero_unauthorized_escalation_in_staging_package():
    """AST Scan: Assert zero unauthorized escalation calls inside staging/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    staging_dir = os.path.join(repo_root, "staging")

    violations = []
    if os.path.exists(staging_dir):
        for root, _, files in os.walk(staging_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr in ("escalate_to_live", "submit_live_order", "bypass_safety_gate"):
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION (Invariant 4J-P4): Staging code contains unsafe escalation calls: {violations}"


def test_ast_audit_zero_broker_sdk_imports_in_staging_package():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in staging/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    staging_dir = os.path.join(repo_root, "staging")
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    if os.path.exists(staging_dir):
        for root, _, files in os.walk(staging_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name.split('.')[0] in disallowed_sdks:
                                    violations.append((os.path.relpath(f_path, repo_root), alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and node.module.split('.')[0] in disallowed_sdks:
                                violations.append((os.path.relpath(f_path, repo_root), node.module))

    assert len(violations) == 0, f"ISOLATION VIOLATION: Staging module imports broker SDK: {violations}"
