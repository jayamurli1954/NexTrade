# tests/test_shadow_safety_audit.py
"""
Shadow Mode Safety Audit Test Suite for NexTrade (Sub-Phase 4G).
Verifies:
1. Zero External Order Submissions: Shadow mode always triggers LiveSafetyGate S12 DENY.
2. AST Code Scan: Zero BrokerAdapter.submit_order() calls in shadow execution modules.
3. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in shadow execution modules.
"""
import ast
import os
import pytest
from unittest.mock import MagicMock

from contracts.execution import ExecutionRequest, OrderSide
from execution.safety_gate import LiveSafetyGate
from execution.shadow_runner import ShadowRunner


def test_shadow_runner_always_triggers_live_safety_gate_s12_deny():
    """Verify ShadowRunner always evaluates LiveSafetyGate S12 to DENY under ExecutionEnvironment.SHADOW."""
    gate = LiveSafetyGate()
    runner = ShadowRunner(safety_gate=gate)

    exec_req = ExecutionRequest(
        execution_request_id="EXREQ-AUDIT-01",
        idempotency_key="IDEM-AUDIT-01",
        risk_decision_id="RD-AUDIT-01",
        symbol="AAPL",
        exchange="NASDAQ",
        order_side=OrderSide.BUY,
        requested_quantity=10,
        approved_quantity=10,
        execution_quantity=10
    )

    rec = runner.process_shadow_execution(exec_req, market_tick_price=150.0, live_trading_enabled=False)

    assert "SHADOW_ENVIRONMENT_NO_DISPATCH" in rec.safety_gate_denial_reasons


def test_ast_audit_zero_broker_submit_in_shadow_modules():
    """AST Scan: Assert zero BrokerAdapter.submit_order() calls in shadow execution modules."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shadow_files = [
        os.path.join(repo_root, "execution", "shadow_engine.py"),
        os.path.join(repo_root, "execution", "shadow_runner.py"),
        os.path.join(repo_root, "execution", "shadow_evaluator.py"),
        os.path.join(repo_root, "storage", "shadow_store.py"),
    ]

    violations = []
    for f_path in shadow_files:
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=f_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "submit_order":
                        violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION: Shadow module invokes submit_order: {violations}"


def test_ast_audit_zero_broker_sdk_imports_in_shadow_modules():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in shadow modules."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shadow_files = [
        os.path.join(repo_root, "execution", "shadow_engine.py"),
        os.path.join(repo_root, "execution", "shadow_runner.py"),
        os.path.join(repo_root, "execution", "shadow_evaluator.py"),
        os.path.join(repo_root, "storage", "shadow_store.py"),
    ]
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    for f_path in shadow_files:
        if os.path.exists(f_path):
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

    assert len(violations) == 0, f"ISOLATION VIOLATION: Shadow module imports broker SDK: {violations}"
