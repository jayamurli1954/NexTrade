# NexTrade Position Sizing Engine Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [risk/position_sizer.py](file:///d:/Back_up/NexTrade/risk/position_sizer.py)  

---

## 1. Architectural Role & Responsibilities

`PositionSizer` is responsible for converting trade signals, stop-loss distances, risk limits, and instrument mechanics into an **authorized, risk-constrained executable quantity** for a single trade request.

```text
                  Signal & OrderRequest
                           │
                           ▼
                  PositionSizer.calculate_quantity()
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
 Risk-per-Trade       Instrument        Capital/Margin
Calculation (Decimal)  Mechanics          Feasibility
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                           ▼
                      SizingResult
```

### Strict Architectural Boundaries:
1. **Quantity Authority**: `Signal.suggested_quantity` is a non-authoritative hint. For `ENTRY` requests, $Q_{approved} = \min(Q_{requested}, Q_{risk\_calculated}, Q_{capital}, Q_{margin})$.
2. **`EXIT` and `REDUCE` Safety**: `REDUCE` authorized size is capped at $Q_{current\_position}$ to prevent accidental position reversals. `EXIT` closes the full open position.
3. **Decimal Financial Arithmetic**: All price, stop loss, risk budget, and trade value calculations use `decimal.Decimal` with explicit tick rounding.
4. **Context-Aware Margin**: Leverages `MarginConstraint`; fails closed (`SizingReason.INSUFFICIENT_MARGIN`) if margin requirement is unknown for margin instruments.
5. **No Portfolio Risk Limits**: Concentration caps (`max_symbol_exposure_pct`, sector limits) belong to Phase 2C (Portfolio Limits Engine).

---

## 2. Mathematical Sizing Pipeline

1. **Tick Alignment & Directional Validation**:
   * Rejects with `PRICE_NOT_TICK_ALIGNED` if entry/stop is not aligned to `tick_size` (e.g. ₹0.05).
   * Long Entry requires $P_{sl} < P_{entry}$.
   * Short Entry requires $P_{sl} > P_{entry}$.
   * Rejects with `STOP_DISTANCE_BELOW_TICK` if $|P_{entry} - P_{sl}| < \text{tick\_size}$.
2. **Effective Risk Budget**:
   * Risk percentage $R_{pct}$ is clamped to $0.25\% \le R_{pct} \le 1.00\%$ (default $0.50\%$).
   * $\text{Risk Amount} = \text{Account Equity} \times (R_{pct} / 100)$.
3. **Raw Risk Quantity**:
   * $Q_{raw} = \lfloor \text{Risk Amount} / |P_{entry} - P_{sl}| \rfloor$.
4. **Lot Size Normalization**:
   * $Q_{lot} = \lfloor Q_{raw} / \text{lot\_size} \rfloor \times \text{lot\_size}$.
   * Rejects with `RISK_SIZE_BELOW_MINIMUM_LOT` if $Q_{raw} < \text{lot\_size}$.
5. **Capital & Margin Feasibility**:
   * Caps quantity against available cash and available margin.
6. **Minimum Economic Trade Value Guard**:
   * Rejects with `BELOW_MINIMUM_TRADE_VALUE` if $Q_{approved} \times P_{entry} < \text{minimum\_economic\_trade\_value}$ (default ₹500.0).

---

## 3. Data Structures & Enums ([risk/position_sizer.py](file:///d:/Back_up/NexTrade/risk/position_sizer.py))

* **`SizingStatus`**: `SIZED` ($Q_{approved} == Q_{requested}$), `PARTIALLY_SIZED` ($0 < Q_{approved} < Q_{requested}$), `REJECTED`, `INVALID_INPUT`.
* **`SizingReason`**: `SUCCESS`, `INVALID_ENTRY_PRICE`, `INVALID_STOP_LOSS`, `INVALID_STOP_DIRECTION`, `PRICE_NOT_TICK_ALIGNED`, `STOP_DISTANCE_BELOW_TICK`, `ZERO_RISK_BUDGET`, `INSUFFICIENT_CAPITAL`, `INSUFFICIENT_MARGIN`, `RISK_SIZE_BELOW_MINIMUM_LOT`, `BELOW_MINIMUM_TRADE_VALUE`, `NO_OPEN_POSITION_TO_REDUCE`, `REQUEST_EXCEEDS_POSITION`.
* **`InstrumentInfo`**: `symbol`, `exchange`, `lot_size` (default 1), `tick_size` (default `Decimal("0.05")`), `minimum_economic_trade_value` (default `Decimal("500.0")`), `margin_constraint`.
* **`SizingResult`**: `@dataclass(frozen=True)` output object with immutable `metrics` mapping.
