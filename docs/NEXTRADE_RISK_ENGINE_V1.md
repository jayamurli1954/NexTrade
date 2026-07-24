# NexTrade Risk Engine Orchestrator Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [risk/risk_engine.py](file:///d:/Back_up/NexTrade/risk/risk_engine.py)  

---

## 1. Architectural Scope & Pre-Trade Control Point

`RiskEngine` is the central, unbypassable pre-trade control point composing Phase 2B (`PositionSizer`), Phase 2C (`PortfolioRiskEvaluator`), and Phase 2D (`KillSwitchManager`) into a single canonical `RiskDecision`.

```text
                  SIGNAL / ORDER REQUEST
                           │
                           ▼
                 PHASE 2E RISK ENGINE ORCHESTRATOR (risk/risk_engine.py)
                           │
  ┌────────────────────────┼────────────────────────┐
  ▼                        ▼                        ▼
Phase 2B PositionSizer   Phase 2C PortfolioRisk   Phase 2D KillSwitchManager
(Single-trade Sizing)    (Portfolio Exposure Caps)(Safety Gates & Breakers)
  │ (Q_2B)                 │ (Q_2C <= Q_2B)         │ (Q_2D <= Q_2C)
  └────────────────────────┼────────────────────────┘
                           │
                           ▼
             Decision Synthesizer & Trace Compiler
                           │
                           ▼
                    Immutable RiskDecision
                           │
  ┌────────────────────────┴────────────────────────┐
  ▼                                                 ▼
RiskDecision.status in (APPROVED, MODIFIED)       RiskDecision.status in (REJECTED, BLOCKED_BY_KILL_SWITCH)
approved_quantity > 0                             approved_quantity == 0
  │                                                 │
  ▼                                                 ▼
Pass to BrokerInterface                           Block Execution
```

---

## 2. Invariants & Decision Pipeline Rules

1. **Master Quantity Chain Invariant**:
   $$0 \le Q_{final} \le Q_{2D} \le Q_{2C} \le Q_{2B} \le Q_{requested}$$
   * Evaluates and enforces that no downstream risk layer may ever increase an authorized quantity.
2. **Unbypassable Execution Rule**:
   $$\text{Order Submission Permitted} \iff \text{RiskDecision.status} \in \{\text{APPROVED}, \text{MODIFIED}\} \text{ AND } Q_{final} > 0$$
3. **Deterministic Pipeline & Short-Circuit Behavior**:
   * Evaluation order: Input Validation $\rightarrow$ 2B Position Sizing $\rightarrow$ 2C Portfolio Exposure Limits $\rightarrow$ 2D Safety Gates.
   * If Phase 2B or Phase 2C returns 0 quantity, evaluation short-circuits with status `REJECTED`.
4. **Auditable Decision Traces**:
   * `RiskDecision` records complete step-by-step metrics (`requested_quantity`, `position_sized_quantity`, `portfolio_approved_quantity`, `kill_switch_authorized_quantity`, `approved_quantity`), `primary_reason`, `limiting_phase`, and timestamp.
5. **Fail-Closed Exception Safety**:
   * If any risk component raises an unexpected exception, `RiskEngine` catches it and fails closed: `status = REJECTED`, `approved_quantity = 0`, `primary_reason = "RISK_ENGINE_INTERNAL_ERROR"`.

---

## 3. Data Structures & Interface ([risk/risk_engine.py](file:///d:/Back_up/NexTrade/risk/risk_engine.py))

* **`RiskEngine`**: Orchestrator class providing `evaluate_order_request()`.
* **`RiskDecision`**: Immutable canonical output dataclass defined in `contracts/risk.py`.
