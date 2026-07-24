# NexTrade Risk Contracts Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [contracts/risk.py](file:///d:/Back_up/NexTrade/contracts/risk.py)  

---

## 1. Risk Evaluation Architecture

`contracts/risk.py` defines the canonical domain data structures for pre-trade risk evaluation, position sizing bounds, kill switch blocking, and risk context snapshots.

```text
                  RiskEngine.evaluate()
                           │
  ┌────────────────────────┼────────────────────────┐
  │ INPUT                  │ STATE                  │ CONFIG
  ▼                        ▼                        ▼
Signal + OrderRequest    RiskContext Snapshot     RiskLimits (Default 0.50%)
  │                        │                        │
  └────────────────────────┼────────────────────────┘
                           │
                           ▼
                  1. Hard Safety Gates (Kill Switch)
                           │
                  2. Position Sizing Engine
                           │
                  3. Portfolio & Exposure Limits
                           │
                           ▼
                     OUTPUT (RiskDecision)
```

---

## 2. Dimensional Intent: `OrderSide` vs `OrderIntent`

NexTrade separates physical trade side from risk intent dimension:

| Field | Enum | Values | Purpose |
| :--- | :--- | :--- | :--- |
| **`OrderSide`** | `OrderSide` | `BUY`, `SELL` | Direct broker execution order side. |
| **`OrderIntent`** | `OrderIntent` | `ENTRY`, `EXIT`, `REDUCE`, `REVERSAL` | Risk dimension relative to portfolio holding. |

### Intent & Safety Gate Matrix:

| Existing Position | OrderSide | OrderIntent | Risk Effect | Hard Safety Gate / Kill Switch Policy |
| :--- | :--- | :--- | :--- | :--- |
| **FLAT** | `BUY` | `ENTRY` | Opens new exposure | ❌ **BLOCKED** if Kill Switch active |
| **LONG** | `SELL` | `REDUCE` | Lowers open size | ✅ **ALLOWED** (Risk-reducing) |
| **LONG** | `SELL` | `EXIT` | Closes position | ✅ **ALLOWED** (Risk-reducing) |
| **LONG** | `SELL` | `REVERSAL` | Flips to Short | ❌ **BLOCKED** (Treated as new `ENTRY` risk) |
| **SHORT** | `BUY` | `REDUCE` | Lowers short size | ✅ **ALLOWED** (Risk-reducing) |
| **SHORT** | `BUY` | `EXIT` | Closes short position | ✅ **ALLOWED** (Risk-reducing) |
| **SHORT** | `BUY` | `REVERSAL` | Flips to Long | ❌ **BLOCKED** (Treated as new `ENTRY` risk) |

---

## 3. Contract Schemas & Specifications

### 3.1 `RiskCheckResult` ([contracts/risk.py](file:///d:/Back_up/NexTrade/contracts/risk.py))
* **Dataclass**: `@dataclass(frozen=True)` `RiskCheckResult`
* **Purpose**: Immutable evaluation output of a single risk rule.
* **Fields**:
  * `rule_name` (`str`): Evaluated rule identifier (e.g. `"MaxDailyLossRule"`).
  * `category` (`RiskRuleCategory`): `KILL_SWITCH`, `POSITION_SIZING`, `ACCOUNT`, `PORTFOLIO`, `EXPOSURE`, `DAILY_LOSS`, `LIQUIDITY`, `BROKER`.
  * `passed` (`bool`): Rule pass/fail indicator.
  * `severity` (`RiskRuleSeverity`): `INFO`, `WARNING`, `BLOCKING`.
  * `reason` (`Optional[str]`): Text rationale.
  * `metrics` (`Mapping[str, Any]`): Immutable proxy dictionary of quantitative metrics.

---

### 3.2 `RiskDecision` ([contracts/risk.py](file:///d:/Back_up/NexTrade/contracts/risk.py))
* **Dataclass**: `@dataclass(frozen=True)` `RiskDecision`
* **Purpose**: Immutable final authorized decision for an order request.
* **Enums**: `RiskDecisionStatus` (`APPROVED`, `MODIFIED`, `REJECTED`, `BLOCKED_BY_KILL_SWITCH`).
* **Fields**:
  * `decision_id` (`str`), `signal_id` (`Optional[str]`), `order_intent` (`OrderIntent`), `decision` (`RiskDecisionStatus`), `requested_quantity` (`int`), `approved_quantity` (`int`), `modification_reason` (`Optional[str]`), `checks_evaluated` (`Tuple[RiskCheckResult, ...]`), `timestamp` (UTC `datetime`).
* **Invariants**:
  * $0 \le \text{approved\_quantity} \le \text{requested\_quantity}$
  * Status `MODIFIED` requires $0 < \text{approved\_quantity} < \text{requested\_quantity}$
  * Status `REJECTED` / `BLOCKED_BY_KILL_SWITCH` requires $\text{approved\_quantity} == 0$
  * Property `is_submittable`: `True` only if decision is `APPROVED` or `MODIFIED` AND $\text{approved\_quantity} > 0$.

---

### 3.3 `RiskLimits` ([contracts/risk.py](file:///d:/Back_up/NexTrade/contracts/risk.py))
* **Dataclass**: `@dataclass(frozen=True)` `RiskLimits`
* **Fields & Invariants**:
  * `min_risk_per_trade_pct` (`0.25%`), **`default_risk_per_trade_pct` (`0.50%`)**, `max_risk_per_trade_pct` (`1.00%`).
  * `max_daily_loss_amount` (`5000.0`), `max_open_positions` (`5`), `max_symbol_exposure_pct` (`20.0`), `max_sector_exposure_pct` (`40.0`).
  * Enforces $0.0 < \text{min} \le \text{default} \le \text{max}$.

---

### 3.4 `RiskContext` ([contracts/risk.py](file:///d:/Back_up/NexTrade/contracts/risk.py))
* **Dataclass**: `@dataclass(frozen=True)` `RiskContext`
* **Purpose**: Immutable point-in-time snapshot of account funds, open positions, open orders, daily P&L, and active kill switch flags used during evaluation.
* **Fields**: `funds` (`FundsInfo`), `open_positions` (`Tuple[Position, ...]`), `open_orders` (`Tuple[Order, ...]`), `daily_realized_pnl` (`float`), `daily_unrealized_pnl` (`float`), `active_kill_switches` (`Mapping[str, bool]`).
