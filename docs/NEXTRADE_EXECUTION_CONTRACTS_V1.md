# NexTrade Execution Domain Contracts Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [contracts/execution.py](file:///d:/Back_up/NexTrade/contracts/execution.py)  

---

## 1. Architectural Scope & Contract Boundaries

`contracts/execution.py` defines the canonical immutable contracts for the NexTrade Execution Plane:
* **`ExecutionStatus`**: Enum representing state machine execution states (`CREATED`, `AUTHORIZED`, `SUBMITTED`, `PARTIALLY_FILLED`, `FILLED`, `REJECTED`, `CANCELLED`, `EXPIRED`, `UNKNOWN`).
* **`ExecutionRequest`**: Immutable dataclass payload capturing authorized execution intent bound to a `risk_decision_id` and an `idempotency_key`.
* **`ExecutionResult`**: Immutable dataclass outcome capturing broker fill metrics and response data.

```text
               RiskDecision (Phase 2E)
                         │
                         ▼
        ExecutionAuthorizationGate (Phase 2H)
                         │
                         ▼
               ExecutionRequest (Phase 3A)
                         │ (0 < Q_exec <= Q_approved <= Q_req)
                         ▼
               ExecutionGateway (Phase 3B)
                         │
                         ▼
               PaperBrokerAdapter (Phase 3C)
                         │
                         ▼
               ExecutionResult (Phase 3A)
                         │ (Invariant E9: Status UNKNOWN -> Mandatory Reconciliation)
                         ▼
               Reconciliation Engine (Phase 3E)
```

---

## 2. Quantity & Safety Invariants

1. **Quantity Chain**:
   $$0 < Q_{execution} \le Q_{approved} \le Q_{requested}$$
2. **Decision & Idempotency Binding**:
   * Every `ExecutionRequest` MUST provide non-empty `execution_request_id`, `idempotency_key`, and `risk_decision_id`.
3. **Fill Math Integrity**:
   $$0 \le Q_{filled} \le Q_{execution}, \quad Q_{remaining} = Q_{execution} - Q_{filled}$$
4. **Invariant E9 (No Retry on Ambiguous Outcome)**:
   $$\text{status} = \text{UNKNOWN} \implies \text{requires\_reconciliation} = \text{True} \land \text{No Automatic Retry}$$
