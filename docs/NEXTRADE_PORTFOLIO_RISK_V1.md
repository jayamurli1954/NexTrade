# NexTrade Portfolio Risk & Exposure Limits Engine Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [risk/risk_limits.py](file:///d:/Back_up/NexTrade/risk/risk_limits.py)  

---

## 1. Architectural Scope & Projected-State Model

`PortfolioRiskEvaluator` evaluates portfolio-wide concentration limits, unique active symbol counts, and cumulative daily loss limits against the **projected post-trade portfolio state**.

```text
               Phase 2B PositionSizer
                         │
                         │ Candidate Quantity (SizingResult.approved_quantity)
                         ▼
        ┌───────────────────────────────────┐
        │  PROJECTED PORTFOLIO STATE MODEL  │
        └────────────────┬──────────────────┘
                         │ (Calculates Post-Trade Portfolio Exposure)
                         ▼
  ┌──────────────────────┼──────────────────────┬──────────────────────┐
  ▼                      ▼                      ▼                      ▼
Projected Symbol Cap   Projected Sector Cap   Projected Symbol Count  Normalized Daily Loss
(max_symbol_exposure)  (max_sector_exposure)  (max_open_positions)   (max_daily_loss_amount)
  │                      │                      │                      │
  └──────────────────────┼──────────────────────┴──────────────────────┘
                         │
                         ▼
              PortfolioCheckResult (approved_quantity, list of RiskCheckResults)
```

### Key Rules & Invariants:
1. **Post-Trade Projection**:
   * `ENTRY`: Projected symbol exposure = existing position value + (candidate quantity $\times$ entry price).
   * `REDUCE` / `EXIT`: Projected symbol exposure = reduced position value.
   * `REVERSAL`: Existing position exposure is cleared ($0$) before calculating new direction entry exposure.
2. **Unique Active Symbol Counting**:
   * `max_open_positions` counts **unique active ticker symbols**, NOT position rows.
   * Add-on `ENTRY` orders for symbols already held do not increment active symbol count.
3. **Lot-Size Preservation**:
   * When concentration limits reduce candidate quantity, approved quantity is rounded down to a valid multiple of `lot_size`.
4. **Positive Normalized Daily Loss**:
   * $\text{daily\_loss} = \max(\text{Decimal("0.0")}, -(\text{daily\_realized\_pnl} + \text{daily\_unrealized\_pnl}))$.
   * Rejects `ENTRY` / `REVERSAL` if $\text{daily\_loss} \ge \text{max\_daily\_loss\_amount}$ (₹5,000.0).
   * **Safety Rule**: **`EXIT` and `REDUCE` orders REMAIN PERMITTED** to lower portfolio risk even when daily loss is breached.
5. **Sector Mapping Handling**:
   * If symbol has no sector entry in `sector_mapping`, records `RiskCheckResult` with `passed = True`, `severity = WARNING`, `reason = "SECTOR_MAPPING_UNAVAILABLE"`.

---

## 2. Protocol & Data Structures ([risk/risk_limits.py](file:///d:/Back_up/NexTrade/risk/risk_limits.py))

* **`PortfolioCheckResult`**: `@dataclass(frozen=True)` output object (`candidate_quantity`, `approved_quantity`, `passed`, `checks_evaluated`, `reason`).
* **`PortfolioRiskEvaluator`**: Evaluator class implementing `evaluate_portfolio_risk()`.
