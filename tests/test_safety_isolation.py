# tests/test_safety_isolation.py
"""
Multi-Level Safety Isolation Test Suite for NexTrade (Sub-Phase 4D).
Verifies architectural un-bypassability of LiveSafetyGate across 3 levels:
1. Level 1 (AST Code Scan): Assert zero direct BrokerAdapter.submit_order() calls outside ExecutionGateway/adapters.
2. Level 2 (Runtime Enforcement): Assert ExecutionGateway rejects dispatches denied by LiveSafetyGate.
3. Level 3 (Integration Flow): Assert end-to-end authorized flow passes through LiveSafetyGate to BrokerAdapter.
"""
import ast
import os
import pytest
from unittest.mock import MagicMock

from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent
from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus, OrderSide
from contracts.safety_contracts import SafetyEvaluationContext, ExecutionEnvironment, SafetyEvaluationResult
from execution.gateway import ExecutionGateway
from execution.safety_gate import LiveSafetyGate
from brokers.paper_adapter import PaperBrokerAdapter


def test_level_1_ast_scan_no_broker_submit_outside_gateway_or_tests():
    """Level 1 AST Scan: Verify BrokerAdapter.submit_order is not invoked directly in core engines."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    disallowed_dirs = ["core", "risk", "protection", "analyzer"]

    violations = []
    for d in disallowed_dirs:
        dir_path = os.path.join(repo_root, d)
        if not os.path.exists(dir_path):
            continue
        for root, _, files in os.walk(dir_path):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr == "submit_order":
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"ARCHITECTURAL VIOLATION: Core code invokes submit_order directly: {violations}"


def test_level_2_runtime_safety_gate_denial_blocks_gateway_execution():
    """Level 2 Runtime Enforcement: ExecutionGateway returns REJECTED when LiveSafetyGate denies."""
    mock_gate = MagicMock()
    mock_gate.live_trading_enabled = False
    mock_gate.environment = ExecutionEnvironment.LIVE
    mock_gate.authorize_dispatch.return_value = SafetyEvaluationResult(
        is_authorized=False,
        barrier_results=[],
        denial_reasons=["LIVE_TRADING_DISABLED"]
    )

    paper_adapter = PaperBrokerAdapter()
    gateway = ExecutionGateway(broker_adapter=paper_adapter, safety_gate=mock_gate)

    # Register risk decision
    decision = RiskDecision(
        decision_id="RD-ISO-01",
        signal_id="SIG-ISO-01",
        order_intent=OrderIntent.ENTRY,
        decision=RiskDecisionStatus.APPROVED,
        requested_quantity=10,
        approved_quantity=10
    )
    gateway.register_risk_decision(decision)

    req = ExecutionRequest(
        execution_request_id="EXREQ-ISO-01",
        idempotency_key="IDEM-ISO-01",
        risk_decision_id="RD-ISO-01",
        symbol="AAPL",
        exchange="NASDAQ",
        order_side=OrderSide.BUY,
        requested_quantity=10,
        approved_quantity=10,
        execution_quantity=10
    )

    res = gateway.execute(req)

    assert res.status == ExecutionStatus.REJECTED
    assert "LIVE_SAFETY_GATE_DENIED" in res.rejection_reason


def test_level_3_end_to_end_authorized_dispatch_flow():
    """Level 3 Integration Flow: Authorized request passes through LiveSafetyGate to BrokerAdapter."""
    safety_gate = LiveSafetyGate()
    paper_adapter = PaperBrokerAdapter()
    gateway = ExecutionGateway(broker_adapter=paper_adapter, safety_gate=safety_gate)

    decision = RiskDecision(
        decision_id="RD-ISO-02",
        signal_id="SIG-ISO-02",
        order_intent=OrderIntent.ENTRY,
        decision=RiskDecisionStatus.APPROVED,
        requested_quantity=5,
        approved_quantity=5
    )
    gateway.register_risk_decision(decision)

    req = ExecutionRequest(
        execution_request_id="EXREQ-ISO-02",
        idempotency_key="IDEM-ISO-02",
        risk_decision_id="RD-ISO-02",
        symbol="MSFT",
        exchange="NASDAQ",
        order_side=OrderSide.BUY,
        requested_quantity=5,
        approved_quantity=5,
        execution_quantity=5
    )

    res = gateway.execute(req)

    assert res.status == ExecutionStatus.FILLED
    assert res.filled_quantity == 5
    assert res.broker_order_id is not None
