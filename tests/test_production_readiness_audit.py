# tests/test_production_readiness_audit.py
"""
Production Readiness Safety Audit Test Suite for NexTrade (Sub-Phase 4M).
Verifies:
1. ProductionReadinessAuditor consolidates 4A–4M certificates into ProductionReadinessCertificate (Invariant 4M-P6).
2. AST Code Scan: Zero UI code calls bypassing LiveSafetyGate or StagingGate (Invariant 4M-P1).
3. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in ui_new/ package.
"""
import ast
import os
import pytest

from audit.production_readiness_auditor import ProductionReadinessAuditor


def test_production_readiness_auditor_consolidation():
    """Verify ProductionReadinessAuditor issues READY certificate consolidating 4A–4M stack (Invariant 4M-P6)."""
    auditor = ProductionReadinessAuditor()
    cert = auditor.audit_production_readiness()

    assert cert.status == "READY"
    assert cert.audit_4h_passed is True
    assert cert.audit_4i_passed is True
    assert cert.staging_4j_passed is True
    assert cert.pilot_4k_passed is True
    assert cert.resilience_4l_passed is True
    assert cert.user_safety_4m_passed is True
    assert len(cert.evidence_hash) == 64


def test_ast_audit_zero_safety_bypass_in_ui_package():
    """AST Scan: Assert zero UI code calls bypassing LiveSafetyGate or StagingGate (Invariant 4M-P1)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ui_dir = os.path.join(repo_root, "ui_new")

    disallowed_calls = {"bypass_safety_gate", "bypass_staging_gate", "submit_direct_to_broker"}

    violations = []
    if os.path.exists(ui_dir):
        for root, _, files in os.walk(ui_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr in disallowed_calls:
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION (Invariant 4M-P1): UI code contains safety bypass calls: {violations}"


def test_ast_audit_zero_broker_sdk_imports_in_ui_package():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in ui_new/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ui_dir = os.path.join(repo_root, "ui_new")
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    if os.path.exists(ui_dir):
        for root, _, files in os.walk(ui_dir):
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

    assert len(violations) == 0, f"ISOLATION VIOLATION: UI module imports broker SDK: {violations}"
