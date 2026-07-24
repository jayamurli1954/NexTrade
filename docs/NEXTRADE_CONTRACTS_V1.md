# NexTrade Canonical Contracts Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [contracts/](file:///d:/Back_up/NexTrade/contracts/)  

---

## 1. Domain Architecture Overview

Phase 1A introduces **broker-independent canonical domain contracts** establishing a clear separation between:
* **Research / Intent (`Signal`)**
* **Execution Instruction (`Order`)**
* **Execution Result / Fill (`Trade`)**
* **Portfolio Holding State (`Position`)**

```text
               RESEARCH / ANALYSIS (InvestMitra / NexTrade Analyzer)
                                │
                                ▼
                             SIGNAL
                    ([contracts/signal.py](file:///d:/Back_up/NexTrade/contracts/signal.py))
                                │
                      Risk Engine Validation
                                │
                                ▼
                              ORDER
                     ([contracts/order.py](file:///d:/Back_up/NexTrade/contracts/order.py))
                                │
                        Broker Execution
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
      Single Fill                               Partial Fills
          │                                           │
          ▼                                           ▼
        TRADE                                      TRADES
 ([contracts/trade.py](file:///d:/Back_up/NexTrade/contracts/trade.py))   ([contracts/trade.py](file:///d:/Back_up/NexTrade/contracts/trade.py))
          │                                           │
          └─────────────────────┬─────────────────────┘
                                │
                                ▼
                            POSITION
                   ([contracts/position.py](file:///d:/Back_up/NexTrade/contracts/position.py))
```

---

## 2. Contract Schemas & Specifications

### 2.1 Trading Signal Contract ([contracts/signal.py](file:///d:/Back_up/NexTrade/contracts/signal.py))
* **Dataclass**: `@dataclass(frozen=True)` `Signal`
* **Purpose**: Represents an immutable strategy recommendation to enter or exit an asset.
* **Fields**:
  * `signal_id` (`str`): Unique signal identifier.
  * `strategy_id` (`str`): Identifier of the generating strategy.
  * `strategy_version` (`str`): Version string (default: `"1.0.0"`).
  * `symbol` (`str`): Trading ticker symbol (e.g., `"RELIANCE"`).
  * `exchange` (`str`): Market exchange (e.g., `"NSE"`, `"NFO"`).
  * `action` (`SignalAction`): `BUY`, `SELL`, `HOLD`, `CLOSE`.
  * `entry_price` (`float`): Suggested price level.
  * `stop_loss` (`float`): Risk stop-loss level.
  * `target_price` (`float`): Take-profit price level.
  * `confidence` (`float`): Score between `0.0` and `1.0`.
  * `timestamp` (`datetime`): Timezone-aware UTC generation timestamp.
  * `expiry` (`datetime`): Timezone-aware UTC expiration timestamp.
  * `source` (`str`): Source system (`"InvestMitra"`, `"NexTrade_Analyzer"`).
  * `suggested_quantity` (`Optional[int]`): Suggestion only; final quantity is computed by `RiskEngine`.
  * `metadata` (`Mapping[str, Any]`): Immutable proxy dictionary for extra parameters.
  * `signature` (`Optional[str]`): HMAC-SHA256 signature for security.
* **Methods**:
  * `is_expired(now: Optional[datetime] = None) -> bool`: Deterministic expiration evaluation.
  * `to_dict() -> Dict[str, Any]`, `from_dict(data: Dict[str, Any]) -> Signal`: Lightweight JSON serialization.

---

### 2.2 Order Lifecycle Contract ([contracts/order.py](file:///d:/Back_up/NexTrade/contracts/order.py))
* **Dataclass**: `@dataclass` `Order`
* **Purpose**: Mutable order intent object tracking execution lifecycle states.
* **Enums**:
  * `OrderSide`: `BUY`, `SELL`.
  * `OrderType`: `MARKET`, `LIMIT`, `STOP_LOSS`, `STOP_LOSS_MARKET`.
  * `OrderStatus`: `CREATED`, `RISK_APPROVED`, `RISK_REJECTED`, `SUBMITTED`, `ACKNOWLEDGED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`.
  * `TimeInForce`: `DAY`, `IOC`, `GTC`.
* **Fields**:
  * `order_id`, `strategy_id`, `symbol`, `exchange`, `side`, `order_type`, `quantity`, `signal_id`, `filled_quantity`, `limit_price`, `stop_price`, `average_fill_price`, `status`, `time_in_force`, `created_at` (UTC), `updated_at` (UTC), `rejection_reason`, `broker_order_id`, `metadata`.
* **Methods**:
  * `update_status(new_status, reason)`: Update state and set `updated_at`.
  * `add_fill(fill_quantity, fill_price)`: Record fill execution, recalculate `average_fill_price`, update status to `PARTIALLY_FILLED` or `FILLED`.

---

### 2.3 Executed Fill Contract ([contracts/trade.py](file:///d:/Back_up/NexTrade/contracts/trade.py))
* **Dataclass**: `@dataclass(frozen=True)` `Trade`
* **Purpose**: Immutable record of an execution fill resulting from an order execution.
* **Note**: A `Trade` represents a single execution fill (not a complete round-trip trade). Multiple `Trade` fills can belong to a single `Order`.
* **Fields**:
  * `trade_id`, `order_id`, `symbol`, `exchange`, `side` (`OrderSide`), `trade_type` (`TradeType`: `ENTRY` / `EXIT`), `quantity`, `price`, `fee`, `slippage`, `timestamp` (UTC), `broker_trade_id`, `metadata`.

---

### 2.4 Portfolio Position State Contract ([contracts/position.py](file:///d:/Back_up/NexTrade/contracts/position.py))
* **Dataclass**: `@dataclass` `Position`
* **Purpose**: Mutable portfolio position state tracking.
* **Enums**:
  * `PositionSide`: `LONG`, `SHORT`, `FLAT`.
  * `PositionStatus`: `OPEN`, `CLOSED`.
* **Fields**:
  * `position_id`, `strategy_id`, `symbol`, `exchange`, `side`, `quantity`, `average_entry_price`, `current_price`, `stop_loss`, `target_price`, `realized_pnl`, `unrealized_pnl`, `status`, `opened_at` (UTC), `closed_at` (UTC), `trade_ids` (`List[str]`), `metadata`.
* **Methods**:
  * `update_market_price(new_price)`: Update current price and compute basic unrealized P&L.
  * `close(exit_price)`: Mark position as closed, update realized P&L, set `side = FLAT`.
