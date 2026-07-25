# contracts/broker_domain.py
"""
Canonical Broker Domain Models for NexTrade (Sub-Phase 4B).
Defines strongly typed, frozen dataclasses and enums representing external broker models.
Excludes Phase 3 core contracts (ExecutionRequest/ExecutionResult) to maintain clean translation boundaries.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List


class BrokerOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class BrokerOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"


class BrokerTimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class BrokerOrderStatus(str, Enum):
    PENDING_SUBMIT = "PENDING_SUBMIT"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BrokerOrderRequest:
    """Canonical, broker-neutral request payload for order placement."""
    nextrade_execution_id: str
    idempotency_key: str
    symbol: str
    side: BrokerOrderSide
    order_type: BrokerOrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trailing_offset: Optional[float] = None
    time_in_force: BrokerTimeInForce = BrokerTimeInForce.DAY
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.nextrade_execution_id:
            raise ValueError("nextrade_execution_id must be a non-empty string")
        if not self.idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        if not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        if self.order_type == BrokerOrderType.LIMIT and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("LIMIT orders require a positive limit_price")
        if self.order_type == BrokerOrderType.STOP and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("STOP orders require a positive stop_price")


@dataclass(frozen=True)
class BrokerOrderModificationRequest:
    """Canonical, broker-neutral request payload for order parameter modification."""
    nextrade_execution_id: str
    broker_order_id: str
    new_quantity: Optional[float] = None
    new_limit_price: Optional[float] = None
    new_stop_price: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.nextrade_execution_id:
            raise ValueError("nextrade_execution_id must be a non-empty string")
        if not self.broker_order_id:
            raise ValueError("broker_order_id must be a non-empty string")
        if self.new_quantity is not None and self.new_quantity <= 0:
            raise ValueError(f"new_quantity must be positive, got {self.new_quantity}")


@dataclass(frozen=True)
class BrokerOrderResult:
    """Canonical, broker-neutral execution result returned from BrokerAdapter."""
    nextrade_execution_id: str
    idempotency_key: str
    status: BrokerOrderStatus
    broker_order_id: Optional[str] = None
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    average_fill_price: float = 0.0
    error_code: str = ""
    error_message: str = ""
    requires_reconciliation: bool = False
    raw_response: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.nextrade_execution_id:
            raise ValueError("nextrade_execution_id must be a non-empty string")
        if not self.idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        if self.filled_quantity < 0:
            raise ValueError("filled_quantity cannot be negative")
        if self.remaining_quantity < 0:
            raise ValueError("remaining_quantity cannot be negative")


@dataclass(frozen=True)
class BrokerFill:
    """Record of a single partial or complete fill reported by a broker."""
    fill_id: str
    broker_order_id: str
    nextrade_execution_id: str
    symbol: str
    fill_quantity: float
    fill_price: float
    fee: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerOrder:
    """Canonical snapshot of an active or historical broker order."""
    broker_order_id: str
    nextrade_execution_id: str
    idempotency_key: str
    symbol: str
    side: BrokerOrderSide
    order_type: BrokerOrderType
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    status: BrokerOrderStatus
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    average_fill_price: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerPosition:
    """Canonical model for an open broker position."""
    symbol: str
    quantity: float
    average_entry_price: float
    current_market_price: float = 0.0
    unrealized_pnl: float = 0.0
    account_id: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerAccount:
    """Canonical model for broker account equity and buying power."""
    account_id: str
    currency: str
    total_equity: float
    buying_power: float
    cash_balance: float
    margin_used: float = 0.0
    is_live: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class BrokerEvent:
    """Canonical model for asynchronous broker callback events."""
    event_id: str
    event_type: str
    broker_order_id: Optional[str]
    nextrade_execution_id: Optional[str]
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
