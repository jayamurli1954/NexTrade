# contracts/order.py
"""
Canonical Order Contract for NexTrade.
Represents an execution instruction and its state lifecycle.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TimeInForce(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Order:
    """
    Mutable order intent object tracking execution lifecycle.
    """
    order_id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    signal_id: Optional[str] = None
    filled_quantity: int = 0
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    average_fill_price: Optional[float] = None
    status: OrderStatus = OrderStatus.CREATED
    time_in_force: TimeInForce = TimeInForce.DAY
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    rejection_reason: Optional[str] = None
    broker_order_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
        if self.updated_at.tzinfo is None:
            self.updated_at = self.updated_at.replace(tzinfo=timezone.utc)

        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")

    def update_status(self, new_status: OrderStatus, reason: Optional[str] = None) -> None:
        """Update order lifecycle status and update timestamp."""
        self.status = new_status
        if reason:
            self.rejection_reason = reason
        self.updated_at = datetime.now(timezone.utc)

    def add_fill(self, fill_quantity: int, fill_price: float) -> None:
        """Record an execution fill on this order."""
        if fill_quantity <= 0:
            raise ValueError(f"Fill quantity must be positive, got {fill_quantity}")
        
        new_filled = self.filled_quantity + fill_quantity
        if new_filled > self.quantity:
            raise ValueError(f"Total filled quantity {new_filled} exceeds order quantity {self.quantity}")

        # Update average fill price
        current_total_val = (self.average_fill_price or 0.0) * self.filled_quantity
        new_total_val = current_total_val + (fill_price * fill_quantity)
        self.average_fill_price = new_total_val / new_filled
        self.filled_quantity = new_filled

        if self.filled_quantity == self.quantity:
            self.update_status(OrderStatus.FILLED)
        else:
            self.update_status(OrderStatus.PARTIALLY_FILLED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary representation."""
        return {
            "order_id": self.order_id,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "average_fill_price": self.average_fill_price,
            "status": self.status.value,
            "time_in_force": self.time_in_force.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "rejection_reason": self.rejection_reason,
            "broker_order_id": self.broker_order_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Order":
        """Instantiate Order from dictionary."""
        return cls(
            order_id=data["order_id"],
            signal_id=data.get("signal_id"),
            strategy_id=data["strategy_id"],
            symbol=data["symbol"],
            exchange=data["exchange"],
            side=OrderSide(data["side"]),
            order_type=OrderType(data["order_type"]),
            quantity=int(data["quantity"]),
            filled_quantity=int(data.get("filled_quantity", 0)),
            limit_price=data.get("limit_price"),
            stop_price=data.get("stop_price"),
            average_fill_price=data.get("average_fill_price"),
            status=OrderStatus(data.get("status", "CREATED")),
            time_in_force=TimeInForce(data.get("time_in_force", "DAY")),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(timezone.utc),
            rejection_reason=data.get("rejection_reason"),
            broker_order_id=data.get("broker_order_id"),
            metadata=data.get("metadata", {}),
        )
