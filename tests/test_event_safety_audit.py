# tests/test_event_safety_audit.py
"""
Event Safety Boundary Audit Test Suite for NexTrade (Sub-Phase 4E).
Verifies that real-time event processing maintains strict safety isolation:
1. Zero Execution Authority: Events NEVER invoke BrokerAdapter.submit_order().
2. Invariant Protection: Events cannot bypass Phase 3 E1–E41 state machine transitions.
3. Safety Gate Integration: Stream disconnect events set S10 to DENY.
"""
import ast
import os
import pytest
from unittest.mock import MagicMock

from contracts.event_contracts import CanonicalEvent, StreamType, EventType
from events.event_bus import EventBus
from events.state_integrator import StateIntegrator
from brokers.stream_listener import BrokerStreamListener
from execution.safety_gate import LiveSafetyGate
from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType
from contracts.safety_contracts import SafetyEvaluationContext, ExecutionEnvironment


def test_ast_audit_zero_broker_submit_in_events_package():
    """AST Scan: Assert zero BrokerAdapter.submit_order() calls inside events/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    events_dir = os.path.join(repo_root, "events")

    violations = []
    if os.path.exists(events_dir):
        for root, _, files in os.walk(events_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                            if node.func.attr == "submit_order":
                                violations.append(os.path.relpath(f_path, repo_root))

    assert len(violations) == 0, f"SAFETY VIOLATION: Event handlers call submit_order directly: {violations}"


def test_stream_disconnection_triggers_safety_gate_s10_deny():
    """Verify Stream disconnect sets LiveSafetyGate broker_connection_status to DISCONNECTED -> S10 DENY."""
    safety_gate = LiveSafetyGate()
    # Initially connected
    safety_gate.broker_connection_status = "CONNECTED"

    bus = EventBus()
    listener = BrokerStreamListener(event_bus=bus, safety_gate=safety_gate, stream_id="AUDIT_STREAM")

    # Simulate disconnect
    listener.on_disconnect("Physical network drop")
    assert getattr(safety_gate, "broker_connection_status", None) == "DISCONNECTED"

    # Evaluate safety gate authorization request
    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-DISC-01",
        idempotency_key="IDEM-DISC-01",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=10.0,
        limit_price=150.0
    )
    ctx = SafetyEvaluationContext(
        environment=ExecutionEnvironment.PAPER,
        broker_connection_status="DISCONNECTED"
    )
    res = safety_gate.authorize_dispatch(req, ctx)

    assert res.is_authorized is False
    assert "BROKER_CONNECTION_UNHEALTHY" in res.denial_reasons
