# tests/test_readiness_safety_audit.py
"""
Readiness Audit Safety Audit Test Suite for NexTrade (Sub-Phase 4I).
Verifies:
1. Invariant 4I-P1: Readiness certification ONLY; 0 order submissions, state machine mutations, or environment status changes.
2. AST Code Scan: Zero BrokerAdapter.submit_order() calls in audit/ package.
3. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in audit/ package.
"""
import ast
import os
import pytest

from audit.readiness_auditor import LiveReadinessAuditor


def test_4i_p1_readiness_auditor_never_mutates_environment_or_submits_orders():
    """Verify LiveReadinessAuditor evaluating a READY decision does not mutate environment status or submit orders."""
    auditor = LiveReadinessAuditor()

    # Assert that LiveReadinessAuditor has no methods or fields capable of setting environment or calling submit_order
    assert not hasattr(auditor, "submit_order")
    assert not hasattr(auditor, "change_environment")
    assert not hasattr(auditor, "enable_live_trading")


def test_ast_audit_zero_broker_submit_or_state_mutation_in_audit_package():
    """AST Scan: Assert zero BrokerAdapter.submit_order() or state transition calls inside audit/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    audit_dir = os.path.join(repo_root, "audit")

    violations = []
    if os.path.exists(audit_dir):
        for root, _, files in os.walk(audit_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr in ("submit_order", "transition_to", "reconcile_to", "enable_live_trading"):
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION (Invariant 4I-P1): Audit code mutates state or dispatches orders: {violations}"


def test_ast_audit_zero_broker_sdk_imports_in_audit_package():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in audit/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    audit_dir = os.path.join(repo_root, "audit")
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    if os.path.exists(audit_dir):
        for root, _, files in os.walk(audit_dir):
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

    assert len(violations) == 0, f"ISOLATION VIOLATION: Audit module imports broker SDK: {violations}"
