# NexTrade Phase 4E — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4E establishes NexTrade's **Event-Driven Integration Layer**, ingesting real-time market data ticks and asynchronous broker order/fill events without weakening Phase 3 state machine invariants (E1–E41) or Phase 4D live gateway safety controls (S1–S12).

---

## Key Core Guarantees & Architectural Boundaries

1. **Zero Execution Authority (Safety Perimeter Rule)**:
   Real-time events may update internal state representations (e.g., position fills, order statuses, market prices) and trigger reconciliation, but **events NEVER create execution authority or trigger order dispatches (`BrokerAdapter.submit_order()`)**.

2. **Validated State Machine Transition Pathway**:
   `StateIntegrator` routes order events strictly through `ExecutionStateMachine.transition_to()` or `ExecutionStateMachine.reconcile_to()`. Direct state mutation is prohibited.

3. **Logical Stream Separation**:
   - `StreamType.MARKET_DATA`: Market price ticks and quote feeds -> updates price feeds & risk context.
   - `StreamType.EXECUTION`: Order status, fills, partial fills, position/account updates -> updates state machine & reconciler.

4. **Scoped Monotonic Sequences**:
   Sequence tracking is scoped per stream ID (`stream_id` + `sequence_id`). Out-of-order events per stream are routed to the Dead-Letter Queue (DLQ).

5. **Auditable Dead-Letter Queue (DLQ)**:
   Stores `DLQRecord` entries with full forensic audit metadata (original payload, stream ID, sequence ID, rejection reason, timestamp, and `replay_eligible` flag).

6. **Automatic Disconnection Reconciliation**:
   Stream disconnect events update `broker_connection_status = "DISCONNECTED"`, causing `LiveSafetyGate` S10 to evaluate to `DENY` and flagging un-reconciled active orders for review.

---

## Safety & Integration Verification Checklist

- [x] All 8 Sub-Phase 4E unit and integration tests passed.
- [x] AST scan confirms 0 `BrokerAdapter.submit_order()` calls inside `events/` package.
- [x] Stream disconnect pushes `LiveSafetyGate` S10 to `DENY`.
- [x] Out-of-order events routed to `AuditableDLQ` with `replay_eligible=True`.
- [x] Duplicate events suppressed and logged to `AuditableDLQ` with `replay_eligible=False`.
- [x] `EventReplayEngine` deterministically replays historical events.
- [x] Phase 3 E1–E41 state machine invariants and Phase 4D S1–S12 safety bounds preserved.
