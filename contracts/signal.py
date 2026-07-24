# contracts/signal.py
"""
Canonical Signal Contract for NexTrade.
Represents an immutable research/strategy signal decision.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Mapping
from types import MappingProxyType


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Signal:
    """
    Immutable trading signal object.
    Represents a strategy recommendation to buy, sell, or close an asset.
    """
    signal_id: str
    strategy_id: str
    symbol: str
    exchange: str
    action: SignalAction
    entry_price: float
    stop_loss: float
    target_price: float
    confidence: float                  # Scale 0.0 to 1.0
    timestamp: datetime                # Timezone-aware UTC timestamp
    expiry: datetime                   # Timezone-aware UTC expiry timestamp
    source: str                        # e.g., "InvestMitra", "NexTrade_Analyzer"
    strategy_version: str = "1.0.0"
    suggested_quantity: Optional[int] = None  # Suggestion only; RiskEngine calculates final size
    metadata: Mapping[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None     # HMAC signature for verification

    def __post_init__(self):
        # Enforce timezone-aware UTC timestamps
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, 'timestamp', self.timestamp.replace(tzinfo=timezone.utc))
        if self.expiry.tzinfo is None:
            object.__setattr__(self, 'expiry', self.expiry.replace(tzinfo=timezone.utc))
            
        # Protect metadata dictionary against mutation by wrapping in MappingProxyType
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', MappingProxyType(dict(self.metadata)))

        # Validate confidence range
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Signal confidence must be between 0.0 and 1.0, got {self.confidence}")

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """
        Check if the signal has expired.
        Deterministic: Accepts an optional timezone-aware 'now' timestamp.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= self.expiry

    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to lightweight JSON-compatible dictionary."""
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "action": self.action.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "expiry": self.expiry.isoformat(),
            "source": self.source,
            "suggested_quantity": self.suggested_quantity,
            "metadata": dict(self.metadata),
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Signal":
        """Instantiate Signal from dictionary representation."""
        return cls(
            signal_id=data["signal_id"],
            strategy_id=data["strategy_id"],
            strategy_version=data.get("strategy_version", "1.0.0"),
            symbol=data["symbol"],
            exchange=data["exchange"],
            action=SignalAction(data["action"]),
            entry_price=float(data["entry_price"]),
            stop_loss=float(data["stop_loss"]),
            target_price=float(data["target_price"]),
            confidence=float(data["confidence"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            expiry=datetime.fromisoformat(data["expiry"]),
            source=data["source"],
            suggested_quantity=data.get("suggested_quantity"),
            metadata=data.get("metadata", {}),
            signature=data.get("signature"),
        )
