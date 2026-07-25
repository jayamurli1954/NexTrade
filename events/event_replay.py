# events/event_replay.py
"""
Deterministic Event Replay Engine for NexTrade (Sub-Phase 4E).
Replays historical log sequences through EventBus for testing, state reconstruction,
and verifying deterministic duplicate suppression and DLQ routing.
"""
from typing import List, Dict, Any
from dataclasses import replace

from contracts.event_contracts import CanonicalEvent
from events.event_bus import EventBus


class EventReplayEngine:
    """
    Replays historical CanonicalEvents through EventBus deterministically.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def replay_events(self, events: List[CanonicalEvent]) -> Dict[str, Any]:
        """
        Replays a list of CanonicalEvents through EventBus in order.
        Returns summary metrics (total_replayed, delivered, dlq_routed).
        """
        initial_dlq_count = self.event_bus.dlq.count
        delivered_count = 0

        for event in events:
            replay_event = replace(event, is_replay=True)
            if self.event_bus.publish(replay_event):
                delivered_count += 1

        final_dlq_count = self.event_bus.dlq.count
        new_dlq_records = final_dlq_count - initial_dlq_count

        return {
            "total_replayed": len(events),
            "delivered": delivered_count,
            "dlq_routed": new_dlq_records,
        }
