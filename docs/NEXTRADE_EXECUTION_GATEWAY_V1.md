# NexTrade Execution Gateway Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [execution/gateway.py](file:///d:/Back_up/NexTrade/execution/gateway.py)  

---

## 1. Architectural Scope & Subsystem Separation

`execution/gateway.py` implements the `ExecutionGateway`, which serves as the canonical entry point for execution requests in NexTrade.

It delegates authorization evaluation directly to `ExecutionAuthorizationGate` (Phase 2H) without duplicating authorization logic, and enforces Decision Binding and Invariant E10 (Idempotency Intent Binding).

```text
                  ExecutionRequest (Phase 3A)
                             │
                             ▼
                 ┌───────────────────────┐
                 │    ExecutionGateway   │ (execution/gateway.py)
                 └───────────┬───────────┘
                             │
            1. Check Invariant E10 (Idempotency Intent Binding)
                             │
            2. Resolve Authoritative RiskDecision (risk_decision_id)
                             │
            3. Verify Quantity Integrity (Q_exec <= Q_approved)
                             │
            4. Delegate to ExecutionAuthorizationGate.can_execute()
                             │
            5. Dispatch to BrokerAdapter (Paper/Sandbox)
                             │
                             ▼
                      ExecutionResult
```

---

## 2. Invariant E10 (Idempotency Intent Binding)

* **Registration**: Every `idempotency_key` is permanently registered with its initial `ExecutionRequest` signature (`execution_request_id`, `risk_decision_id`, `symbol`, `order_side`, `execution_quantity`).
* **Identical Re-submission**: Reusing the key with identical parameters returns the cached `ExecutionResult` without duplicate broker execution attempts.
* **Conflicting Re-submission**: Reusing the key with conflicting execution parameters MUST be rejected immediately with `ExecutionStatus.REJECTED` and `rejection_reason = "IDEMPOTENCY_CONFLICT..."`.
