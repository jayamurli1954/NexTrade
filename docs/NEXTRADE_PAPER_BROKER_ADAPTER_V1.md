# NexTrade Paper Broker Adapter Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [brokers/paper_adapter.py](file:///d:/Back_up/NexTrade/brokers/paper_adapter.py)  

---

## 1. Architectural Scope & Isolation

`brokers/paper_adapter.py` implements `PaperBrokerAdapter`, fulfilling the canonical `BrokerInterface` protocol ([contracts/broker.py](file:///d:/Back_up/NexTrade/contracts/broker.py)).

It wraps the existing `PaperTrader` simulator ([order_manager/paper_trader.py](file:///d:/Back_up/NexTrade/order_manager/paper_trader.py)) safely without altering core simulator logic or connecting to live broker APIs.

```text
                  ExecutionGateway (Phase 3B)
                             │
                             ▼
                 ┌───────────────────────┐
                 │   PaperBrokerAdapter  │ (brokers/paper_adapter.py)
                 └───────────┬───────────┘
                             │
            1. Validate ExecutionRequest Invariants
                             │
            2. Enforce Invariant E13 (No Live Connectivity)
                             │
            3. Execute via PaperTrader.execute_order()
                             │
            4. Pre- vs Post-Submission Error Isolation (E14 & E15)
                             │
            5. Return Canonical ExecutionResult (E12 Quantity Preservation)
                             │
                             ▼
                    PaperTrader Simulator
```

---

## 2. The 6 Sub-Phase 3C Invariants (E11 – E16)

1. **E11 (Broker Isolation)**: `ExecutionGateway` $\rightarrow$ `BrokerInterface` $\rightarrow$ `PaperBrokerAdapter`. No direct broker calls from `RiskEngine`.
2. **E12 (Quantity Preservation)**: $0 \le Q_{filled} \le Q_{execution} \le Q_{approved}$.
3. **E13 (No Live Connectivity)**: Provably paper-only execution without live API keys/endpoints.
4. **E14 (Unknown-State Preservation)**: Post-submission boundary timeouts produce `status = UNKNOWN` with `requires_reconciliation = True`. No automatic retry.
5. **E15 (Broker Error Isolation)**: Deterministic pre-submission errors produce `status = REJECTED` (`requires_reconciliation = False`).
6. **E16 (Execution Traceability)**: Full lineage (`execution_request_id`, `risk_decision_id`, `signal_id`, `broker_order_id`) preserved in `ExecutionResult`.
