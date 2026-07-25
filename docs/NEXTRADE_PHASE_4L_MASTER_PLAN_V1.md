# NexTrade Phase 4L — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4L constructs NexTrade's **Operational Resilience & Incident Certification Subsystem**, establishing an un-bypassable failure-recovery framework, incident escalation controller, recovery epoch idempotency guard, position truth recovery engine, disaster recovery backup manager, and 6 certified chaos drills prior to Production Readiness Certification (v4.2 milestone).

---

## Master Safety Invariants (4L-P1 — 4L-P13)

```text
4L-P1  Fail-Closed Incident Response (Failures force REDUCE_ONLY or HARD_HALT)
4L-P2  No Silent Recovery (Recovery requires explicit human recovery tokens)
4L-P3  Broker Disconnect Safety (Disconnect forces BROKER_DISCONNECTED and locks dispatch)
4L-P4  Recovery Is Not Execution Authorization (Recovery resets to SAFE; NO live dispatch authority)
4L-P5  Idempotency & Recovery Epoch Guard (Tracks recovery_epoch; prevents duplicate orders/fills)
4L-P6  Deterministic Replay & Stale Event Protection (Stale events older than window discarded)
4L-P7  Position Truth Dominance & Recovery Epoch (Broker position truth overrides internal state)
4L-P8  Incident Escalation & Operator Ack (CRITICAL/FATAL events require operator acknowledgement)
4L-P9  Evidence Preservation (Logs, DB entries, DLQ records survive crashes/restarts)
4L-P10 Disaster Recovery & Backup Restore Integrity (Backup restore preserves audit lineage)
4L-P11 Executable Chaos Drill Certification (6 mandatory drills each produce certified result)
4L-P12 Decision Precedence (REJECT > HOLD > READY)
4L-P13 Resilience Certificate Hash Determinism (Deterministic SHA-256 evidence fingerprint)
```

---

## Architecture Diagram

```text
                    OPERATIONAL FAULT & INCIDENT INPUTS
  ┌─────────────────────────────────────────────────────────────┐
  │ Broker Disconnect Event     (StreamListener Disconnect)     │
  │ Network Timeout / Stale State (SafetyGate / Gateway)        │
  │ Position Quantity Mismatch   (PositionReconciler)           │
  │ Unhandled DLQ Spike          (AuditableDLQ)                 │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
                     IncidentManager (4L-2)
          (Logs IncidentRecord & Enforces Fail-Closed Action)
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
       HARD_HALT                                 REDUCE_ONLY
   (All Execution Blocked)                 (Risk-Reducing Orders Only)
            │                                         │
            └────────────────────┬────────────────────┘
                                 │
                                 ▼
           IdempotencyGuard & Recovery Epoch (4L-4, 4L-5)
     (Tracks Recovery Epoch; Prevents Duplicate Orders/Fills)
                                 │
                                 ▼
                   ChaosRunner Certification (4L-8)
             (Executes 6 Mandatory Resilience Drills)
                                 │
                                 ▼
              Operational Resilience Certificate (4L-10)
          (SQLite DB + JSONL Diagnostic Log with SHA-256)
```

---

## Safety & Governance Verification Checklist

- [x] All 8 Sub-Phase 4L unit and integration tests passed.
- [x] `IncidentManager` triggers fail-closed actions (`HARD_HALT` / `REDUCE_ONLY`) and requires operator ACK.
- [x] `DisconnectHandler` handles stream disconnects and locks dispatch until position reconciliation passes.
- [x] `IdempotencyGuard` advances `recovery_epoch` and rejects duplicate orders/fills persistently.
- [x] `DLQRecoveryEngine` enforces deterministic event replay and stale event rejection.
- [x] `ResilienceBackupManager` creates point-in-time SQLite backups and verifies restore integrity.
- [x] `ChaosRunner` certifies 6 mandatory drills and evaluates `READY` certificate under `REJECT > HOLD > READY` precedence.
- [x] AST scan confirms 0 execution-authority escalation calls in `resilience/` package.
- [x] AST scan confirms 0 broker SDK imports (`ibapi`, `ib_insync`, etc.) in `resilience/` package.
