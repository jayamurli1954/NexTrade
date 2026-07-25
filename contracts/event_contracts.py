# contracts/event_contracts.py
"""
Canonical Event Contracts & Domain Models for NexTrade (Sub-Phase 4E).
Defines strongly typed, frozen models for event-driven integration, logical stream separation,
auditable Dead-Letter Queue (DLQ) records, and scoped sequence deduplication.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import threading
from typing import Dict, Any, List, Optional, Set


class StreamType(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    EXECUTION = "EXECUTION"


class EventType(str, Enum):
    TICK_PRICE = "TICK_PRICE"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_UPDATE = "POSITION_UPDATE"
    ACCOUNT_UPDATE = "ACCOUNT_UPDATE"
    DISCONNECT = "DISCONNECT"
    RECONNECT = "RECONNECT"


@dataclass(frozen=True)
class CanonicalEvent:
    """
    Immutable canonical event structure for all real-time market data and order events.
    """
    event_id: str
    stream_id: str
    sequence_id: int
    stream_type: StreamType
    event_type: EventType
    payload: Dict[str, Any]
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_replay: bool = False


@dataclass(frozen=True)
class DLQRecord:
    """
    Forensic Dead-Letter Queue record storing rejected, out-of-order, or corrupt events.
    """
    dlq_id: str
    event: CanonicalEvent
    rejection_reason: str
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    replay_eligible: bool = True


class EventDeduplicator:
    """
    Thread-safe deduplicator tracking processed event IDs and scoped sequence numbers per stream_id.
    """

    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self._processed_event_ids: Set[str] = set()
        self._event_id_order: List[str] = []
        self._stream_sequences: Dict[str, int] = {}
        self._lock = threading.RLock()

    def is_duplicate(self, event_id: str) -> bool:
        """Returns True if event_id has already been processed."""
        with self._lock:
            return event_id in self._processed_event_ids

    def is_out_of_order(self, stream_id: str, sequence_id: int) -> bool:
        """
        Returns True if sequence_id is less than or equal to the highest recorded sequence_id for stream_id.
        """
        with self._lock:
            last_seq = self._stream_sequences.get(stream_id, -1)
            return sequence_id <= last_seq

    def record_event(self, stream_id: str, sequence_id: int, event_id: str) -> None:
        """Records sequence ID and event ID into deduplication registry."""
        with self._lock:
            self._processed_event_ids.add(event_id)
            self._event_id_order.append(event_id)
            self._stream_sequences[stream_id] = max(self._stream_sequences.get(stream_id, -1), sequence_id)

            # Evict oldest event IDs if exceeding max_history
            if len(self._event_id_order) > self.max_history:
                oldest = self._event_id_order.pop(0)
                self._processed_event_ids.discard(oldest)

    def reset(self) -> None:
        """Resets all deduplication and sequence history."""
        with self._lock:
            self._processed_event_ids.clear()
            self._event_id_order.clear()
            self._stream_sequences.clear()
