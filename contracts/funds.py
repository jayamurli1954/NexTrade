# contracts/funds.py
"""
Canonical Funds Contract for NexTrade.
Represents broker-independent account capital, margin, and equity state.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FundsInfo:
    """
    Immutable domain representation of account funds, margin, and collateral.
    Independent of market data or broker-specific schemas.
    """
    available_cash: float
    used_margin: float
    available_margin: float
    total_collateral: float = 0.0
    total_equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    currency: str = "INR"
    as_of: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.as_of.tzinfo is None:
            object.__setattr__(self, 'as_of', self.as_of.replace(tzinfo=timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert FundsInfo to lightweight dictionary representation."""
        return {
            "available_cash": self.available_cash,
            "used_margin": self.used_margin,
            "available_margin": self.available_margin,
            "total_collateral": self.total_collateral,
            "total_equity": self.total_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "currency": self.currency,
            "as_of": self.as_of.isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FundsInfo":
        """Instantiate FundsInfo from dictionary."""
        return cls(
            available_cash=float(data.get("available_cash", 0.0)),
            used_margin=float(data.get("used_margin", 0.0)),
            available_margin=float(data.get("available_margin", 0.0)),
            total_collateral=float(data.get("total_collateral", 0.0)),
            total_equity=float(data.get("total_equity", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            currency=data.get("currency", "INR"),
            as_of=datetime.fromisoformat(data["as_of"]) if "as_of" in data else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )
