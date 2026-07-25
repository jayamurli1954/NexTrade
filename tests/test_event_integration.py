# tests/test_event_integration.py
"""
Adversarial Event Integration Test Suite for NexTrade (Sub-Phase 4E).
Verifies event normalization, stream separation, duplicate suppression, out-of-order sequence isolation,
DLQ record audit metadata, state integration, and deterministic event replay.
"""
import pytest
from datetime import datetime, timezone

from contracts.broker_domain import (
    BrokerEvent,
    BrokerOrderStatus,
)
from contracts.event_contracts import (
    CanonicalEvent,
    StreamType,
    EventType,
    EventDeduplicator,
)
from execution.state_machine import ExecutionStateMachine
from events.event_normalizer import EventNormalizer
from events.event_bus import EventBus
from events.state_integrator import StateIntegrator
from events.event_replay import EventReplayEngine
from brokers.stream_listener import BrokerStreamListener


def test_event_normalization():
    """Verify EventNormalizer correctly maps BrokerEvent to CanonicalEvent."""
    b_event = BrokerEvent(
        event_id="EVT-RAW-001",
        event_type="FILLED",
        broker_order_id="BRK-101",
        nextrade_execution_id="EXEC-101",
        payload={
            "filled_quantity": 10,
            "remaining_quantity": 0,
            "average_fill_price": 150.0
        }
    )

    c_event = EventNormalizer.normalize_broker_event(b_event, stream_id="STREAM_A", sequence_id=1)

    assert c_event.event_id == "EVT-RAW-001"
    assert c_event.stream_id == "STREAM_A"
    assert c_event.sequence_id == 1
    assert c_event.stream_type == StreamType.EXECUTION
    assert c_event.event_type == EventType.ORDER_FILLED
    assert c_event.payload["filled_quantity"] == 10


def test_duplicate_event_suppression_and_dlq_routing():
    """Verify duplicate events are suppressed and routed to DLQ with replay_eligible=False."""
    bus = EventBus()
    event1 = CanonicalEvent(
        event_id="EVT-DUP-01",
        stream_id="STREAM_A",
        sequence_id=1,
        stream_type=StreamType.EXECUTION,
        event_type=EventType.ORDER_SUBMITTED,
        payload={"nextrade_execution_id": "EXEC-01"},
        source="TEST"
    )

    # First publication succeeds
    assert bus.publish(event1) is True
    assert bus.dlq.count == 0

    # Duplicate publication fails and routes to DLQ
    assert bus.publish(event1) is False
    assert bus.dlq.count == 1

    record = bus.dlq.get_records()[0]
    assert record.event.event_id == "EVT-DUP-01"
    assert "DUPLICATE_EVENT" in record.rejection_reason
    assert record.replay_eligible is False


def test_out_of_order_sequence_isolation_per_stream():
    """Verify out-of-order sequence IDs per stream are routed to DLQ."""
    bus = EventBus()

    e1 = CanonicalEvent(
        event_id="EVT-SEQ-1",
        stream_id="STREAM_A",
        sequence_id=10,
        stream_type=StreamType.EXECUTION,
        event_type=EventType.ORDER_SUBMITTED,
        payload={},
        source="TEST"
    )
    e2 = CanonicalEvent(
        event_id="EVT-SEQ-2",
        stream_id="STREAM_A",
        sequence_id=5,  # Out of order! (5 <= 10)
        stream_type=StreamType.EXECUTION,
        event_type=EventType.ORDER_FILLED,
        payload={},
        source="TEST"
    )

    assert bus.publish(e1) is True
    assert bus.publish(e2) is False

    assert bus.dlq.count == 1
    record = bus.dlq.get_records()[0]
    assert "OUT_OF_ORDER_SEQUENCE" in record.rejection_reason
    assert record.replay_eligible is True


def test_state_integrator_validated_pathway():
    """Verify StateIntegrator updates ExecutionStateMachine via validated transition_to()."""
    from contracts.execution import ExecutionStatus
    sm = ExecutionStateMachine(execution_request_id="EXEC-INT-01", initial_status=ExecutionStatus.AUTHORIZED)
    integrator = StateIntegrator()
    integrator.register_state_machine("EXEC-INT-01", sm)

    event_sub = CanonicalEvent(
        event_id="EVT-SUB-01",
        stream_id="STREAM_A",
        sequence_id=1,
        stream_type=StreamType.EXECUTION,
        event_type=EventType.ORDER_SUBMITTED,
        payload={"nextrade_execution_id": "EXEC-INT-01"},
        source="TEST"
    )

    event_fill = CanonicalEvent(
        event_id="EVT-FILL-01",
        stream_id="STREAM_A",
        sequence_id=2,
        stream_type=StreamType.EXECUTION,
        event_type=EventType.ORDER_FILLED,
        payload={"nextrade_execution_id": "EXEC-INT-01"},
        source="TEST"
    )

    assert integrator.handle_event(event_sub) is True
    assert sm.current_status == ExecutionStatus.SUBMITTED

    assert integrator.handle_event(event_fill) is True
    assert sm.current_status == ExecutionStatus.FILLED


def test_stream_listener_disconnection_handling():
    """Verify BrokerStreamListener.on_disconnect publishes DISCONNECT event and triggers safety gate S10."""
    bus = EventBus()
    mock_gate = type("MockSafetyGate", (), {"broker_connection_status": "CONNECTED"})()

    listener = BrokerStreamListener(event_bus=bus, safety_gate=mock_gate, stream_id="STREAM_TEST")
    assert listener.on_disconnect("Socket drop") is True

    assert mock_gate.broker_connection_status == "DISCONNECTED"


def test_deterministic_event_replay():
    """Verify EventReplayEngine replays historical events through EventBus deterministically."""
    bus = EventBus()
    replay_engine = EventReplayEngine(bus)

    events = [
        CanonicalEvent(
            event_id=f"EVT-REPLAY-{i}",
            stream_id="STREAM_REP",
            sequence_id=i,
            stream_type=StreamType.MARKET_DATA,
            event_type=EventType.TICK_PRICE,
            payload={"symbol": "AAPL", "price": 150.0 + i},
            source="TEST"
        )
        for i in range(1, 6)
    ]

    metrics = replay_engine.replay_events(events)

    assert metrics["total_replayed"] == 5
    assert metrics["delivered"] == 5
    assert metrics["dlq_routed"] == 0
