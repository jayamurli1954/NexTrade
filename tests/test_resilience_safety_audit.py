# tests/test_resilience_safety_audit.py
"""
Operational Resilience Safety Audit Test Suite for NexTrade (Sub-Phase 4L).
Verifies:
1. Invariant 4L-P4: Recovery Is Not Execution Authorization (Recovery resets incident mode to SAFE, but DOES NOT grant execution authority).
2. AST Code Scan: Zero execution-authority escalation calls in resilience/ package.
3. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in resilience/ package.
"""
import ast
import os
import pytest

from resilience.incident_manager import IncidentManager


def test_4l_p4_recovery_never_grants_execution_authority():
    """Verify IncidentManager.reset_incident_state does not grant execution authority (Invariant 4L-P4)."""
    im = IncidentManager()
    assert not hasattr(im, "authorize_execution")
    assert not hasattr(im, "grant_staging_access")

    # Resetting incident state leaves system in NORMAL incident mode, requiring separate authorization chain
    ok, msg = im.reset_incident_state("OP-REC-01")
    assert ok is True
    assert im.current_mode == "NORMAL"


def test_ast_audit_zero_execution_escalation_in_resilience_package():
    """AST Scan: Assert zero execution-authority escalation calls inside resilience/ package (Invariant 4L-P4)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resilience_dir = os.path.join(repo_root, "resilience")

    disallowed_calls = {"escalate_to_production", "enable_unrestricted_live", "authorize_staging_order", "submit_order"}

    violations = []
    if os.path.exists(resilience_dir):
        for root, _, files in os.walk(resilience_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr in disallowed_calls:
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION (Invariant 4L-P4): Resilience code contains execution escalation calls: {violations}"


def test_ast_audit_zero_broker_sdk_imports_in_resilience_package():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in resilience/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resilience_dir = os.path.join(repo_root, "resilience")
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    if os.path.exists(resilience_dir):
        for root, _, files in os.walk(resilience_dir):
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

    assert len(violations) == 0, f"ISOLATION VIOLATION: Resilience module imports broker SDK: {violations}"
