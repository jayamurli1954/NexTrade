# NexTrade Risk Engine Integration Test Suite Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [tests/test_risk_engine_integration.py](file:///d:/Back_up/NexTrade/tests/test_risk_engine_integration.py)  

---

## 1. Architectural Scope & Orchestration Flow

`TestRiskEngineIntegration` verifies the end-to-end composition across Phase 2B (`PositionSizer`), Phase 2C (`PortfolioRiskEvaluator`), Phase 2D (`KillSwitchManager`), Phase 2E (`RiskEngine` Orchestrator), and Phase 2F (`RiskAuditLogger`).

```text
SIGNAL / ORDER REQUEST
        │
        ▼
┌──────────────────────────────┐
│ Phase 2E RiskEngine          │ (risk/risk_engine.py)
│ Canonical Orchestrator       │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
     2B       2C       2D
   Sizing   Portfolio  Kill
            Risk       Switch
       │       │        │
       └───────┼────────┘
               ▼
        Immutable RiskDecision
               │
               ├──────────────► Execution Boundary (NOT CONNECTED YET)
               │
               ▼
       Phase 2F Audit Logger (risk/audit_logger.py)
               │
       ┌───────┴────────┐
       ▼                ▼
 Authoritative       Reporting
 JSONL               CSV
       │
       ▼
 verify_integrity()
```

---

## 2. Verified Master Invariants & Exit Criteria

1. **Master Quantity Chain Invariant**:
   $$0 \le Q_{final} \le Q_{2D} \le Q_{2C} \le Q_{2B} \le Q_{requested}$$
   * The master quantity invariant is verified for all scenarios that exercise the RiskEngine quantity pipeline. Audit-only scenarios independently verify audit durability, integrity, and correspondence properties.

2. **Execution Neutrality**:
   * Entire `OrderRequest` $\rightarrow$ `RiskEngine` $\rightarrow$ `RiskDecision` $\rightarrow$ `AuditLogger` $\rightarrow$ `AuditEvent` pipeline produces **zero broker / execution side-effects** (`0` calls to `BrokerInterface`, `AngelOne`, or `PaperTrader`).
3. **Exact Decision-to-Audit Correspondence**:
   * `RiskDecision` attributes match `AuditEvent` fields exactly (`decision_id`, `decision_status`, `requested_quantity`, `approved_quantity`, `primary_reason`).
4. **Authoritative JSONL & CSV Projection**:
   * JSONL remains the authoritative, tamper-evident record. CSV failures degrade logger health without corrupting JSONL integrity.
