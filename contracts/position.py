# contracts/position.py
"""
Canonical Position Contract for NexTrade.
Represents an active or closed portfolio holding position state.
Note: Full accounting, fees, and tax calculations are handled separately by P&L/Risk engines.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Position:
    """
    Mutable portfolio position state model.
    """
    position_id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: PositionSide
    quantity: int
    average_entry_price: float
    current_price: float = 0.0
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    opened_at: datetime = field(default_factory=_utc_now)
    closed_at: Optional[datetime] = None
    trade_ids: List[str] = field(default_factory=list)  # Associated trade fill IDs
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.opened_at.tzinfo is None:
            self.opened_at = self.opened_at.replace(tzinfo=timezone.utc)
        if self.closed_at and self.closed_at.tzinfo is None:
            self.closed_at = self.closed_at.replace(tzinfo=timezone.utc)

    def update_market_price(self, new_price: float) -> None:
        """Update current market price and compute basic unrealized P&L."""
        self.current_price = new_price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.average_entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.average_entry_price - self.current_price) * self.quantity

    def close(self, exit_price: float) -> None:
        """Mark position as closed."""
        self.update_market_price(exit_price)
        self.realized_pnl = self.unrealized_pnl
        self.unrealized_pnl = 0.0
        self.quantity = 0
        self.side = PositionSide.FLAT
        self.status = PositionStatus.CLOSED
        self.closed_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary representation."""
        return {
            "position_id": self.position_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value,
            "quantity": self.quantity,
            "average_entry_price": self.average_entry_price,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "status": self.status.value,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "trade_ids": list(self.trade_ids),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        """Instantiate Position from dictionary."""
        return cls(
            position_id=data["position_id"],
            strategy_id=data["strategy_id"],
            symbol=data["symbol"],
            exchange=data["exchange"],
            side=PositionSide(data["side"]),
            quantity=int(data["quantity"]),
            average_entry_price=float(data["average_entry_price"]),
            current_price=float(data.get("current_price", 0.0)),
            stop_loss=data.get("stop_loss"),
            target_price=data.get("target_price"),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            status=PositionStatus(data.get("status", "OPEN")),
            opened_at=datetime.fromisoformat(data["opened_at"]) if "opened_at" in data else datetime.now(timezone.utc),
            closed_at=datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,
            trade_ids=data.get("trade_ids", []),
            metadata=data.get("metadata", {}),
        )
