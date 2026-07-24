# NexTrade Sub-Phase 3E — Reconciliation Engine Architectural Specification & Invariants

## Executive Summary
Sub-Phase 3E establishes the **Reconciliation Engine** (`execution/reconciler.py`) and canonical domain contracts (`contracts/reconciliation.py`). The Reconciliation Engine acts as the authoritative synchronization layer between internal execution state machines, protection lifecycles, and actual broker order/fill reports.

---

## The 5 Phase 3E Architectural Invariants

### 1. Invariant E29 — Reconciliation Authority Boundary
- Only `ReconciliationEngine` may invoke `ExecutionStateMachine.reconcile_to(new_status, authority_key)`.
- Strategies, `ProtectionLifecycleManager`, and `ExecutionGateway` are prohibited from resolving `UNKNOWN` states directly.
- Direct standard transitions (`transition_to()`) from `UNKNOWN` to terminal states raise `ValueError`.

### 2. Invariant E30 — Position Quantity Conservation
For every reconciled execution:
- **Entry Order**: \( Q_{\text{open\_new}} = Q_{\text{open\_old}} + Q_{\text{entry\_filled\_delta}} \)
- **Exit Order**: \( Q_{\text{open\_new}} = Q_{\text{open\_old}} - Q_{\text{exit\_filled\_delta}} \)
- Guaranteed invariants:
  - \( 0 \le Q_{\text{open\_new}} \)
  - \( Q_{\text{protected}} \le Q_{\text{open\_new}} \)
  - \( Q_{\text{filled\_total}} \le Q_{\text{requested}} \)

### 3. Invariant E31 — Cumulative Fill Monotonicity
- Multi-step broker fill updates use cumulative fill delta accounting:
  \[
  \Delta Q_{\text{fill}} = \max(0, \text{CumulativeFilled}_{\text{authoritative}} - \text{CumulativeFilled}_{\text{reconciled}})
  \]
- Re-processing execution reports or late broker fills calculates non-overlapping deltas, preventing double-counting or ledger corruption.

### 4. Invariant E32 — Authoritative Broker State with Discrepancy Escalation
- Broker order status and cumulative fills are authoritative for broker order status.
- Portfolio and position quantity mismatches generate immutable `ReconciliationDiscrepancy` records with `CRITICAL` or `FATAL` severity for audit log escalation rather than being silently overwritten.

### 5. Invariant E33 — Deterministic Reconciliation Idempotency Identity
- Every broker state observation generates a deterministic key:
  \[
  \text{key} = \text{hash}(\text{broker\_order\_id}, \text{status}, \text{cumulative\_filled}, \text{fill\_price}, \text{event\_id})
  \]
- Processing identical broker state observations returns the cached `ReconciliationResult` with zero additional fill delta or position mutations.

---

## Protection Restoration Lifecycle

```text
                    UNKNOWN Exit Execution
                               │
                               ▼
                    Reconciliation Engine
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
         FILLED         PARTIALLY_FILLED       REJECTED
            │                  │                  │
            ▼                  ▼                  ▼
     Open Qty -> 0      Open Qty -> Q_rem    Open Qty -> Unchanged
     State -> CLOSED    State -> ACTIVE      State -> ACTIVE
```

- When an exit execution is resolved, `ProtectionLifecycleManager` transitions out of `RECONCILIATION_REQUIRED` back to `CLOSED` (for 100% fill) or `ACTIVE` (for rejection or partial fill update).
- `ReconciliationEngine` does **NOT** issue new broker execution requests directly. Subsequent exit decisions are initiated by `ProtectionLifecycleManager` and pass through `ExecutionGateway` to enforce authorization and idempotency controls.

---

## Test Verification Summary
- **Total Test Suite Pass**: 165 / 165 passed in 6.94s (`python -m pytest tests`).
- **Paper Trader Regression**: 100% PASS (`python -m pytest tests/test_paper_adapter.py`).
- **Tag**: `v2.5-phase-3e-reconciler`
