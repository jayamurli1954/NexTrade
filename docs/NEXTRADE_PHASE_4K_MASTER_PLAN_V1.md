# NexTrade Phase 4K — Master Architecture Document (v1.0)

## Executive Summary

Sub-Phase 4K constructs NexTrade's **Controlled Live Pilot Operations Framework**, establishing an operational governance model, executable pre-flight certification gate, human-approved order lifecycle, real-time position reconciliation, fault injection harness, and immutable session evidence package prior to Operational Resilience Certification (4L).

---

## Master Safety Invariants (4K-P1 — 4K-P12)

```text
4K-P1  Pilot Success Is Evidence, Not Authority (Zero automatic escalation to production)
4K-P2  Explicit Stage Transition Authorization (Stage 1 -> 2 -> 3 requires human sign-off)
4K-P3  Executable Pre-Flight Certification (100% pre-flight checklist certification)
4K-P4  Human Approval Binding (Per-order human approval binding in Stage 1)
4K-P5  Effective Limits Monotonicity (Effective limit = MIN(4J, 4K); can only tighten)
4K-P6  Immutable Order and Session Lineage Context
4K-P7  Position Truth & Reconciliation Lock (Position mismatch locks order dispatch)
4K-P8  Failure Injection Isolation (Fault injection restricted to paper/sandbox)
4K-P9  Immutable Pilot Evidence (SHA-256 pilot evidence package)
4K-P10 Session Expiry & Explicit Closure (Finite session validity; expired sessions close)
4K-P11 No Automatic Recovery from Safety Locks
4K-P12 No Automatic Escalation to Production
```

---

## Architecture Diagram

```text
               STAGING AUTHORIZATION & 4A–4J STACK
┌─────────────────────────────────────────────────────────────┐
│ 4H PROMOTE Certificate  (storage/promotion_decision.db)     │
│ 4I READY Certificate    (storage/readiness_audit.db)        │
│ 4J Staging Token        (storage/controlled_live_staging.db)│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                   PreflightGate (4K-2)
        (100% Pre-flight Checklist Certification)
                               │
                               ▼
                 PilotSessionManager (4K-3)
         (Stage 1 / Stage 2 / Stage 3 Execution Window)
                               │
                               ▼
             Human Approval Order Pipeline (4K-4)
        (Requires explicit human sign-off per order)
                               │
                               ▼
                   StagingGate (4J Boundary)
                               │
                               ▼
                  BrokerAdapter & Market
                               │
                               ▼
              PositionReconciler & Monitor (4K-5, 4K-6)
     (Verifies position truth vs broker; locks on delta)
                               │
                               ▼
             Immutable Pilot Evidence Store (4K-8)
        (SQLite DB + JSONL Diagnostic Log with SHA-256)
```

---

## Safety & Governance Verification Checklist

- [x] All 10 Sub-Phase 4K unit and integration tests passed.
- [x] Executable `PreflightGate` issues signed `PreflightCertificate` on 100% checklist pass.
- [x] `PilotSessionManager` requires explicit operator re-authorization for stage escalation.
- [x] `PilotOrderPipeline` validates per-order human approvals in Stage 1 pilot.
- [x] `PositionReconciler` triggers `RECONCILIATION_LOCK` on position quantity mismatch.
- [x] `FailureInjector` strictly denies fault injection in `LIVE` environment.
- [x] AST scan confirms 0 production escalation calls in `pilot/` package.
- [x] AST scan confirms 0 broker SDK imports (`ibapi`, `ib_insync`, etc.) in `pilot/` package.
- [x] Dual persistence in SQLite (`pilot_operations.db`) and JSONL (`pilot_operations.jsonl`) verified.
