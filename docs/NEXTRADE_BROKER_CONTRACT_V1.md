# NexTrade Abstract Broker Contract Specification v1.0

**Date:** July 24, 2026  
**Repository Path:** `D:\Back_up\NexTrade`  
**Module Location:** [contracts/broker.py](file:///d:/Back_up/NexTrade/contracts/broker.py)  

---

## 1. Architectural Boundary & Responsibilities

`BrokerInterface` defines the abstract protocol for order execution, order management, position tracking, and account capital state.

```text
                    NEXTRADE DOMAIN
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
       Signal           Broker         DataProvider
  (contracts/signal.py) (contracts/broker.py) (contracts/data_provider_v1.py)
          │                │                │
          │                │                │
          │                ▼                ▼
          │           Execution          Market Data
          │                │
          │       ┌────────┼─────────┐
          │       ▼        ▼         ▼
          │     Order     Trade    Position
          │
          └──────────────┐
                         ▼
                    Risk Engine
```

### Strict Architectural Boundaries:
1. **Execution vs Market Data**: `BrokerInterface` owns order placement, cancellation, modification, and account funds. It does **not** expose market quotes, ticker subscriptions, or historical candles (which belong exclusively to `DataProviderInterface`).
2. **Domain Object Isolation**: All broker interface methods return NexTrade domain dataclasses (`Order`, `Trade`, `Position`, `FundsInfo`), preventing broker-specific API models (e.g. Angel One API JSON) from polluting internal domain logic.
3. **Neutral Funds Contract**: Account capital and margin state are represented by `FundsInfo` in [contracts/funds.py](file:///d:/Back_up/NexTrade/contracts/funds.py), completely decoupled from `DataProvider` contracts.
4. **Session / Authentication Independence**: Authentication and connection lifecycles are owned by concrete broker adapters (`AngelOneBroker`, `PaperBroker`), keeping `BrokerInterface` focused purely on execution capabilities.

---

## 2. Broker Exception Hierarchy

All broker errors are normalized into a clean domain exception tree in `contracts/broker.py`:

```python
BrokerError (Base Exception)
 ├── NetworkError (Socket error, timeout, connectivity loss)
 ├── InsufficientFundsError (Insufficient cash or margin for order)
 ├── OrderNotFoundError (Order ID not found on broker)
 ├── OrderValidationError (Invalid price, tick size, or parameters)
 └── BrokerAuthenticationError (Session expired, invalid API key)
```

---

## 3. Abstract Method Protocols

```python
class BrokerInterface(ABC):

    @abstractmethod
    def place_order(self, order: Order, idempotency_key: Optional[str] = None) -> Order:
        """Submit domain Order; returns updated Order (status = SUBMITTED / FILLED)."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """Cancel open order by order_id; returns updated Order (status = CANCELLED)."""
        pass

    @abstractmethod
    def modify_order(self, order_id: str, changes: OrderModification) -> Order:
        """Modify open order using extensible OrderModification dataclass; returns updated Order."""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        """Reconcile and return current status of an order."""
        pass

    @abstractmethod
    def get_open_orders(self) -> List[Order]:
        """Fetch active/pending domain Orders."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Fetch active portfolio positions mapped to domain Position models."""
        pass

    @abstractmethod
    def get_account_funds(self) -> FundsInfo:
        """Fetch current cash and margin mapped to domain FundsInfo."""
        pass

    @abstractmethod
    def get_trades(self, order_id: Optional[str] = None) -> List[Trade]:
        """Fetch execution fills mapped to domain Trade models."""
        pass
```

---

## 4. Idempotency & Reconciliation Design

1. **NexTrade-Level Idempotency**: `place_order(order, idempotency_key)` provides client-side deduplication. Concrete broker adapters must determine whether native broker idempotency is supported; where native support is absent, adapters maintain persistent client-side tracking and order reconciliation to prevent duplicate order placement during network retries.
2. **Order Modification Extensibility**: `OrderModification` ([contracts/order.py](file:///d:/Back_up/NexTrade/contracts/order.py)) supports updating `new_quantity`, `new_limit_price`, `new_stop_price`, and `new_time_in_force`.
