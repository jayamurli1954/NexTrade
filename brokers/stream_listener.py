# brokers/stream_listener.py
"""
Broker Stream Listener for NexTrade (Sub-Phase 4E).
Connects BrokerEventStream objects to EventBus, normalizing raw events
and driving fail-closed disconnection handling on LiveSafetyGate S10.
"""
from typing import Optional, Any
from datetime import datetime, timezone

from contracts.broker_domain import BrokerEvent, BrokerOrderStatus
from contracts.event_contracts import CanonicalEvent, StreamType, EventType
from events.event_normalizer import EventNormalizer
from events.event_bus import EventBus


class BrokerStreamListener:
    """
    Listens to BrokerEventStreams, normalizes incoming events, and publishes to EventBus.
    """

    def __init__(self, event_bus: EventBus, safety_gate: Optional[Any] = None, stream_id: str = "BROKER_STREAM_01"):
        self.event_bus = event_bus
        self.safety_gate = safety_gate
        self.stream_id = stream_id
        self._sequence_counter = 0

    def on_broker_event(self, broker_event: BrokerEvent) -> bool:
        """
        Callback handler invoked when a BrokerEvent arrives from a BrokerEventStream.
        """
        self._sequence_counter += 1

        canonical_event = EventNormalizer.normalize_broker_event(
            broker_event=broker_event,
            stream_id=self.stream_id,
            sequence_id=self._sequence_counter,
            source="BROKER_STREAM"
        )

        return self.event_bus.publish(canonical_event)

    def on_disconnect(self, reason: str = "Stream connection lost") -> bool:
        """
        Handles stream disconnection:
        1. Publishes DISCONNECT event to EventBus.
        2. Sets broker_connection_status = 'DISCONNECTED' on safety_gate (triggers S10 DENY).
        """
        self._sequence_counter += 1

        disconnect_event = CanonicalEvent(
            event_id=f"DISC-{self._sequence_counter}",
            stream_id=self.stream_id,
            sequence_id=self._sequence_counter,
            stream_type=StreamType.EXECUTION,
            event_type=EventType.DISCONNECT,
            payload={"reason": reason},
            source="BROKER_STREAM",
            timestamp=datetime.now(timezone.utc)
        )

        # Update safety gate connection status if configured
        if self.safety_gate is not None and hasattr(self.safety_gate, "broker_connection_status"):
            self.safety_gate.broker_connection_status = "DISCONNECTED"

        return self.event_bus.publish(disconnect_event)
