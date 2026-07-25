# NexTrade Phase 4F — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4F constructs NexTrade's **Unified Observability & Alerting Framework**, providing real-time telemetry, structured health reporting, and threshold-based incident alerting across all Phase 4 sub-systems (Safety Gate, Execution Gateway, Broker Adapters, Event Bus, DLQ, and Reconciler) prior to Shadow Mode (4G) and Live Staging (4J).

---

## Architectural Principles & Guarantees

1. **Read-Only Visibility Rule (Zero Execution Authority)**:
   Observability components (`MetricsRegistry`, `AlertEngine`, `ObservabilityManager`, `HealthExporter`) are strictly **visibility-only**. They detect, classify, and report system states, but **they MUST NEVER create, modify, or bypass execution authority, mutate state, or dispatch orders**.

2. **Strict Separation of Control vs Alerting**:
   - `LiveSafetyGate`: Decides execution authorization (`PASS` vs `DENY`).
   - `ExecutionGateway`: Handles sole dispatch execution.
   - `AlertEngine`: Reports anomalies to logs, console, or dashboards.

3. **Best-Effort & Failure-Isolated Telemetry**:
   Telemetry operations wrap internal logic in try-except guards. Telemetry failures swallow exceptions and never crash core execution paths or block callers.

4. **Non-Blocking & Bounded Exporters**:
   `HealthExporter` executes asynchronously or via bounded output buffers.

5. **7-Pillar Telemetry Metrics Taxonomy**:
   - `SAFETY`: S1–S12 evaluations, denials, MFA token status, daily loss tracking
   - `GATEWAY`: Execution requests, submission latency, fill rates, slippage
   - `BROKER_SESSION`: Connection status, heartbeats, reconnect backoff counters
   - `EVENT_BUS`: Throughput msg/sec, delivery latency, sequence gaps
   - `RECONCILIATION`: Pending un-reconciled orders count, discrepancy rates
   - `DLQ`: DLQ record count, duplicate rate, out-of-order sequence rate
   - `SYSTEM_HEALTH`: Subsystem health scores & active alert counts

6. **Explicit Alert Metadata**:
   Every `AlertRecord` records `alert_id`, `severity` (`INFO`, `WARNING`, `CRITICAL`, `FATAL`), `source_subsystem`, `condition`, `threshold`, `recommended_action`, `timestamp`, and `metrics_snapshot`.

---

## Safety & Integration Verification Checklist

- [x] All 7 Sub-Phase 4F unit and integration tests passed.
- [x] AST scan confirms 0 order submission or state transition calls inside `observability/` package.
- [x] AST scan confirms 0 broker SDK imports inside `observability/` package.
- [x] Telemetry exceptions are failure-isolated and swallowed without crashing execution.
- [x] Staleness indicator (`report.is_stale()`) models health report age.
- [x] Phase 3 E1–E41 state machine invariants and Phase 4D S1–S12 safety bounds preserved.
