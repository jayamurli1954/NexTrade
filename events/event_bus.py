# events/event_bus.py
"""
Thread-Safe Event Bus & Auditable Dead-Letter Queue (DLQ) for NexTrade (Sub-Phase 4E).
Provides pub/sub messaging with logical stream separation (MARKET_DATA vs EXECUTION),
scoped sequence validation, duplicate suppression, and forensic DLQ auditing.
"""
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, List, Callable, Optional, Set

from contracts.event_contracts import (
    CanonicalEvent,
    DLQRecord,
    StreamType,
    EventType,
    EventDeduplicator,
)


class AuditableDLQ:
    """
    Forensic Dead-Letter Queue storing rejected, out-of-order, or corrupt events.
    """

    def __init__(self):
        self._records: Dict[str, DLQRecord] = {}
        self._lock = threading.RLock()

    def add_record(self, event: CanonicalEvent, reason: str, replay_eligible: bool = True) -> DLQRecord:
        """Adds an event to DLQ with audit metadata."""
        with self._lock:
            dlq_id = f"DLQ-{uuid.uuid4().hex[:12].upper()}"
            record = DLQRecord(
                dlq_id=dlq_id,
                event=event,
                rejection_reason=reason,
                received_at=datetime.now(timezone.utc),
                replay_eligible=replay_eligible
            )
            self._records[dlq_id] = record
            return record

    def get_records(self) -> List[DLQRecord]:
        """Returns all DLQ records."""
        with self._lock:
            return list(self._records.values())

    def get_record(self, dlq_id: str) -> Optional[DLQRecord]:
        """Returns a specific DLQ record by ID."""
        with self._lock:
            return self._records.get(dlq_id)

    def clear(self) -> None:
        """Clears all DLQ records."""
        with self._lock:
            self._records.clear()

    @property
    def count(self) -> int:
        """Returns count of DLQ records."""
        with self._lock:
            return len(self._records)


class EventBus:
    """
    Thread-safe event bus enforcing stream separation, deduplication, and subscriber dispatch.
    """

    def __init__(self, deduplicator: Optional[EventDeduplicator] = None):
        self.deduplicator = deduplicator or EventDeduplicator()
        self.dlq = AuditableDLQ()
        self._subscribers: Dict[StreamType, List[Callable[[CanonicalEvent], None]]] = {
            StreamType.MARKET_DATA: [],
            StreamType.EXECUTION: [],
        }
        self._lock = threading.RLock()

    def subscribe(self, stream_type: StreamType, handler: Callable[[CanonicalEvent], None]) -> None:
        """Subscribes a handler function to a specific StreamType."""
        with self._lock:
            if handler not in self._subscribers[stream_type]:
                self._subscribers[stream_type].append(handler)

    def unsubscribe(self, stream_type: StreamType, handler: Callable[[CanonicalEvent], None]) -> None:
        """Unsubscribes a handler function from a StreamType."""
        with self._lock:
            if handler in self._subscribers[stream_type]:
                self._subscribers[stream_type].remove(handler)

    def publish(self, event: CanonicalEvent) -> bool:
        """
        Publishes a CanonicalEvent to subscribers after deduplication and sequence validation.
        Returns True if delivered; False if routed to DLQ.
        """
        if not isinstance(event, CanonicalEvent):
            raise ValueError(f"Expected CanonicalEvent instance, got {type(event).__name__}")

        with self._lock:
            # 1. Duplicate Suppression Check
            if self.deduplicator.is_duplicate(event.event_id):
                self.dlq.add_record(event, f"DUPLICATE_EVENT: Event ID '{event.event_id}' already processed", replay_eligible=False)
                return False

            # 2. Out-Of-Order Sequence Check per stream_id
            if self.deduplicator.is_out_of_order(event.stream_id, event.sequence_id):
                self.dlq.add_record(
                    event,
                    f"OUT_OF_ORDER_SEQUENCE: Sequence ID {event.sequence_id} <= previous sequence for stream '{event.stream_id}'",
                    replay_eligible=True
                )
                return False

            # Record event in deduplicator registry
            self.deduplicator.record_event(event.stream_id, event.sequence_id, event.event_id)

            # Dispatch to subscribers of stream_type
            handlers = list(self._subscribers.get(event.stream_type, []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as ex:
                # Handler exception does not crash bus; log to DLQ
                self.dlq.add_record(event, f"HANDLER_EXCEPTION: {type(ex).__name__}: {str(ex)}", replay_eligible=True)

        return True
