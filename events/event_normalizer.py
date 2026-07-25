# events/event_normalizer.py
"""
Event Normalization Layer for NexTrade (Sub-Phase 4E).
Transforms raw broker events (BrokerEvent) or dictionary stream messages
into strongly-typed, schema-validated CanonicalEvent objects.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from contracts.broker_domain import BrokerEvent
from contracts.event_contracts import (
    CanonicalEvent,
    StreamType,
    EventType,
)


class EventNormalizer:
    """
    Normalizes raw broker event representations into CanonicalEvent instances.
    """

    @staticmethod
    def normalize_broker_event(
        broker_event: BrokerEvent,
        stream_id: str = "DEFAULT_STREAM",
        sequence_id: int = 1,
        source: str = "IBKR"
    ) -> CanonicalEvent:
        """
        Normalizes a typed BrokerEvent domain object into a CanonicalEvent.
        """
        if not isinstance(broker_event, BrokerEvent):
            raise ValueError(f"Expected BrokerEvent instance, got {type(broker_event).__name__}")

        evt_type_str = str(broker_event.event_type).upper()
        if "SUBMIT" in evt_type_str:
            mapped_event_type = EventType.ORDER_SUBMITTED
        elif "PARTIAL" in evt_type_str:
            mapped_event_type = EventType.ORDER_PARTIALLY_FILLED
        elif "FILL" in evt_type_str:
            mapped_event_type = EventType.ORDER_FILLED
        elif "CANCEL" in evt_type_str:
            mapped_event_type = EventType.ORDER_CANCELLED
        elif "REJECT" in evt_type_str:
            mapped_event_type = EventType.ORDER_REJECTED
        else:
            mapped_event_type = EventType.ORDER_REJECTED

        payload = {
            "broker_order_id": broker_event.broker_order_id,
            "nextrade_execution_id": broker_event.nextrade_execution_id,
            "event_type": broker_event.event_type,
            **(broker_event.payload or {})
        }

        return CanonicalEvent(
            event_id=broker_event.event_id or f"EVT-{uuid.uuid4().hex[:12].upper()}",
            stream_id=stream_id,
            sequence_id=sequence_id,
            stream_type=StreamType.EXECUTION,
            event_type=mapped_event_type,
            payload=payload,
            source=source,
            timestamp=broker_event.timestamp or datetime.now(timezone.utc)
        )

    @staticmethod
    def normalize_market_tick(
        symbol: str,
        price: float,
        volume: float = 0.0,
        stream_id: str = "TICK_STREAM",
        sequence_id: int = 1,
        source: str = "IBKR"
    ) -> CanonicalEvent:
        """
        Constructs a CanonicalEvent for a market price tick.
        """
        if not symbol or price <= 0:
            raise ValueError(f"Invalid market tick parameters: symbol='{symbol}', price={price}")

        payload = {
            "symbol": symbol,
            "price": price,
            "volume": volume,
        }

        return CanonicalEvent(
            event_id=f"TICK-{uuid.uuid4().hex[:12].upper()}",
            stream_id=stream_id,
            sequence_id=sequence_id,
            stream_type=StreamType.MARKET_DATA,
            event_type=EventType.TICK_PRICE,
            payload=payload,
            source=source,
            timestamp=datetime.now(timezone.utc)
        )
