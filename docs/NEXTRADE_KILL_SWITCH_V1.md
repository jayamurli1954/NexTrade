# NexTrade Multi-Level System Kill Switch & Circuit Breakers Engine Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [risk/kill_switch.py](file:///d:/Back_up/NexTrade/risk/kill_switch.py)  

---

## 1. Architectural Scope & Precedence Hierarchy

`KillSwitchManager` provides unbypassable system-wide emergency safety gates, fine-grained control scopes, stateful circuit breaker enforcement, and atomic persistence.

### Downstream Quantity Invariant:
$$Q_{final} \le Q_{2D} \le Q_{2C} \le Q_{2B} \le Q_{requested}$$

Where $Q_{2D}$ is authorized as:
* For `ENTRY` / `REVERSAL`: $Q_{2D} = Q_{2C}$ if kill switch is inactive; $Q_{2D} = 0$ if kill switch is active.
* For `EXIT` / `REDUCE`: $Q_{2D} = Q_{2C}$ (permitted by risk policy, subject to broker availability).

```text
               Phase 2B PositionSizer (Q_2B)
                         │
                         ▼
               Phase 2C PortfolioRiskEvaluator (Q_2C)
                         │
                         ▼
        ┌──────────────────────────────────┐
        │  PHASE 2D MULTI-LEVEL KILL SWITCH│ (risk/kill_switch.py)
        └────────────────┬─────────────────┘
                         │ (Precedence Engine & State Persistence)
                         ▼
  ┌──────────────────────┼──────────────────────┬──────────────────────┐
  ▼                      ▼                      ▼                      ▼
Global Kill Switch    Broker Pause           Strategy Pause         Symbol Block
(Priority 1)          (Priority 2)           (Priority 3)           (Priority 4)
  │                      │                      │                      │
  └──────────────────────┼──────────────────────┴──────────────────────┘
                         │
  ┌──────────────────────┼──────────────────────┬──────────────────────┐
  ▼                      ▼                      ▼                      ▼
System Health Breaker Stale Data Breaker    Daily Loss Breaker    Consecutive Losses
(Priority 5)          (Priority 6)           (Priority 7)           (Priority 8)
```

---

## 2. Key Rules & Invariants

1. **Precedence Hierarchy**:
   * Evaluates in order: `GLOBAL` (1) > `BROKER` (2) > `STRATEGY` (3) > `SYMBOL` (4) > `SYSTEM_HEALTH` (5) > `STALE_DATA` (6) > `DAILY_LOSS` (7) > `CONSECUTIVE_LOSS` (8). Returns highest priority active blocker.
2. **Action Policy Rule**:
   * Risk-increasing actions (`ENTRY`, `REVERSAL`) are **BLOCKED** ($Q_{2D} = 0$).
   * Risk-reducing actions (`EXIT`, `REDUCE`) are **PERMITTED** ($Q_{2D} = Q_{2C}$) by risk policy.
3. **Execution Availability Gate**:
   * If `broker_connectivity` is marked offline, even `EXIT` and `REDUCE` orders are rejected (`is_blocked = True`, `authorized_quantity = 0`, `reason = "BROKER_UNAVAILABLE"`).
4. **Atomic Persistence & Fail-Closed Recovery**:
   * State (`logs/kill_switch_state.json`) uses `"schema_version": 1`.
   * Write sequence: `.tmp` $\rightarrow$ `os.fsync` $\rightarrow$ `os.replace`.
   * If state file is corrupted or has an unsupported schema version, manager fails closed into a `GLOBAL` blocked state (`reason = "STATE_PERSISTENCE_FAILURE"`).
5. **Explicit Reset Operations**:
   * Requires explicit individual reset calls (`reset_global()`, `reset_broker()`, `reset_strategy()`, `reset_symbol()`, `reset_circuit_breaker()`) with audit justification (`reason` & `source`). Universal `reset_all()` is removed.

---

## 3. Data Structures & Interface ([risk/kill_switch.py](file:///d:/Back_up/NexTrade/risk/kill_switch.py))

* **`KillSwitchCheckResult`**: `@dataclass(frozen=True)` output object (`is_blocked`, `candidate_quantity`, `authorized_quantity`, `blocking_level`, `breaker_type`, `reason`, `metrics`).
* **`ScopeAuditRecord`**: Audit tracking struct (`triggered_at`, `trigger_reason`, `trigger_source`, `reset_at`, `reset_reason`, `reset_source`).
* **`KillSwitchManager`**: State machine class managing thread-safe safety gates.
