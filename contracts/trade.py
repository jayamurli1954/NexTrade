# contracts/trade.py
"""
Canonical Trade Contract for NexTrade.
Represents an immutable execution fill resulting from an order execution.
Note: A Trade represents a single execution fill, not a complete round-trip trade.
Multiple Trades can belong to a single Order.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Mapping
from types import MappingProxyType

from contracts.order import OrderSide


class TradeType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True)
class Trade:
    """
    Immutable execution fill record.
    """
    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: OrderSide                      # Typed OrderSide (BUY / SELL)
    trade_type: TradeType                 # ENTRY / EXIT fill
    quantity: int
    price: float
    fee: float = 0.0
    slippage: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    broker_trade_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, 'timestamp', self.timestamp.replace(tzinfo=timezone.utc))

        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', MappingProxyType(dict(self.metadata)))

        if self.quantity <= 0:
            raise ValueError(f"Trade fill quantity must be positive, got {self.quantity}")
        if self.price <= 0:
            raise ValueError(f"Trade fill price must be positive, got {self.price}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert Trade fill to lightweight dictionary."""
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "trade_type": self.trade_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "fee": self.fee,
            "slippage": self.slippage,
            "timestamp": self.timestamp.isoformat(),
            "broker_trade_id": self.broker_trade_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trade":
        """Instantiate Trade fill from dictionary."""
        return cls(
            trade_id=data["trade_id"],
            order_id=data["order_id"],
            symbol=data["symbol"],
            exchange=data["exchange"],
            side=OrderSide(data["side"]),
            trade_type=TradeType(data["trade_type"]),
            quantity=int(data["quantity"]),
            price=float(data["price"]),
            fee=float(data.get("fee", 0.0)),
            slippage=float(data.get("slippage", 0.0)),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
            broker_trade_id=data.get("broker_trade_id"),
            metadata=data.get("metadata", {}),
        )
