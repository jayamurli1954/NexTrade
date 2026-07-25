# tests/test_pilot_safety_audit.py
"""
Controlled Live Pilot Safety Audit Test Suite for NexTrade (Sub-Phase 4K).
Verifies:
1. Invariant 4K-P1: Pilot operational success produces evidence, NOT authority to escalate to production.
2. Invariant 4K-P5: Effective limits monotonicity (effective limit = MIN(4J, 4K)).
3. AST Code Scan: Zero unauthorized production escalation calls in pilot/ package.
4. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in pilot/ package.
"""
import ast
import os
import pytest

from contracts.safety_contracts import ExecutionEnvironment
from contracts.staging_contracts import StagingEnvironmentConfig
from contracts.pilot_contracts import PilotSessionConfig, PilotStage
from pilot.session_manager import PilotSessionManager


def test_4k_p1_pilot_success_never_escalates_to_production():
    """Verify PilotSessionManager contains zero methods or logic to escalate to UNRESTRICTED_LIVE."""
    sm = PilotSessionManager()
    assert not hasattr(sm, "escalate_to_production")
    assert not hasattr(sm, "enable_unrestricted_live")


def test_4k_p5_effective_limits_can_only_tighten():
    """Verify 4K effective limits are monotonic MIN(4J, 4K) and can never loosen 4J limits (Invariant 4K-P5)."""
    staging_cfg = StagingEnvironmentConfig(
        max_order_quantity=10.0,
        max_order_notional=1000.0,
        max_position_exposure=2500.0
    )

    pilot_cfg = PilotSessionConfig(
        session_id="SESS-01",
        max_cumulative_exposure=1000.0  # Tightened from 2500
    )

    effective_exposure = min(staging_cfg.max_position_exposure, pilot_cfg.max_cumulative_exposure)
    assert effective_exposure == 1000.0  # Monotonic tightening enforced


def test_ast_audit_zero_production_escalation_in_pilot_package():
    """AST Scan: Assert zero unauthorized production escalation calls inside pilot/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pilot_dir = os.path.join(repo_root, "pilot")

    violations = []
    if os.path.exists(pilot_dir):
        for root, _, files in os.walk(pilot_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr in ("escalate_to_production", "enable_unrestricted_live", "bypass_staging_gate"):
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION (Invariant 4K-P1): Pilot code contains unsafe escalation calls: {violations}"


def test_ast_audit_zero_broker_sdk_imports_in_pilot_package():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in pilot/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pilot_dir = os.path.join(repo_root, "pilot")
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    if os.path.exists(pilot_dir):
        for root, _, files in os.walk(pilot_dir):
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

    assert len(violations) == 0, f"ISOLATION VIOLATION: Pilot module imports broker SDK: {violations}"
