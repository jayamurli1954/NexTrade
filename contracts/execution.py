# contracts/execution.py
"""
Canonical Execution Domain Contracts for NexTrade (Sub-Phase 3A).
Defines immutable contracts for ExecutionStatus, ExecutionRequest, and ExecutionResult.
Enforces execution quantity invariants: 0 < execution_quantity <= approved_quantity <= requested_quantity,
idempotency key binding, decision binding, and Invariant E9 (reconciliation required on UNKNOWN status).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Optional, Dict, Any, List, Tuple
from types import MappingProxyType

from contracts.order import OrderSide


class ExecutionStatus(str, Enum):
    """
    Execution status resulting from broker execution attempt.
    """
    CREATED = "CREATED"                    # Initialized execution request
    AUTHORIZED = "AUTHORIZED"              # Passed ExecutionAuthorizationGate
    SUBMITTED = "SUBMITTED"                # Sent to broker adapter
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Partial fill executed
    FILLED = "FILLED"                      # 100% execution quantity filled
    REJECTED = "REJECTED"                  # Broker rejected request
    CANCELLED = "CANCELLED"                # Order cancelled before fill
    EXPIRED = "EXPIRED"                    # Order expired before fill
    UNKNOWN = "UNKNOWN"                    # Indeterminate outcome (network timeout); retry prohibited without reconciliation


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Immutable request payload for order execution.
    Must be traceable to an authorized RiskDecision and a unique idempotency_key.
    """
    execution_request_id: str
    idempotency_key: str
    risk_decision_id: str
    symbol: str
    exchange: str
    order_side: OrderSide
    requested_quantity: int
    approved_quantity: int
    execution_quantity: int
    signal_id: Optional[str] = None
    strategy_id: Optional[str] = None
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.execution_request_id or not isinstance(self.execution_request_id, str):
            raise ValueError("execution_request_id must be a non-empty string")

        if not self.idempotency_key or not isinstance(self.idempotency_key, str):
            raise ValueError("idempotency_key must be a non-empty string")

        if not self.risk_decision_id or not isinstance(self.risk_decision_id, str):
            raise ValueError("risk_decision_id must be a non-empty string")

        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError("symbol must be a non-empty string")

        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

        # Quantity Invariants: 0 < execution_quantity <= approved_quantity <= requested_quantity
        if self.execution_quantity <= 0:
            raise ValueError(f"execution_quantity must be positive, got {self.execution_quantity}")

        if self.approved_quantity <= 0:
            raise ValueError(f"approved_quantity must be positive, got {self.approved_quantity}")

        if self.requested_quantity <= 0:
            raise ValueError(f"requested_quantity must be positive, got {self.requested_quantity}")

        if self.execution_quantity > self.approved_quantity:
            raise ValueError(
                f"execution_quantity ({self.execution_quantity}) cannot exceed approved_quantity ({self.approved_quantity})"
            )

        if self.approved_quantity > self.requested_quantity:
            raise ValueError(
                f"approved_quantity ({self.approved_quantity}) cannot exceed requested_quantity ({self.requested_quantity})"
            )

        if self.limit_price is not None:
            if math.isnan(self.limit_price) or math.isinf(self.limit_price) or self.limit_price <= 0:
                raise ValueError(f"limit_price must be positive float, got {self.limit_price}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert ExecutionRequest to dictionary representation."""
        return {
            "execution_request_id": self.execution_request_id,
            "idempotency_key": self.idempotency_key,
            "risk_decision_id": self.risk_decision_id,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "order_side": self.order_side.value if isinstance(self.order_side, Enum) else str(self.order_side),
            "requested_quantity": self.requested_quantity,
            "approved_quantity": self.approved_quantity,
            "execution_quantity": self.execution_quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class ExecutionResult:
    """
    Immutable result outcome of broker execution attempt.
    """
    execution_id: str
    execution_request_id: str
    risk_decision_id: str
    status: ExecutionStatus
    requested_quantity: int
    execution_quantity: int
    filled_quantity: int
    remaining_quantity: int
    average_fill_price: float
    broker_order_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.execution_id or not isinstance(self.execution_id, str):
            raise ValueError("execution_id must be a non-empty string")

        if not self.execution_request_id or not isinstance(self.execution_request_id, str):
            raise ValueError("execution_request_id must be a non-empty string")

        if not self.risk_decision_id or not isinstance(self.risk_decision_id, str):
            raise ValueError("risk_decision_id must be a non-empty string")

        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

        # Fill Metric Invariants
        if self.filled_quantity < 0:
            raise ValueError(f"filled_quantity must be non-negative, got {self.filled_quantity}")

        if self.filled_quantity > self.execution_quantity:
            raise ValueError(
                f"filled_quantity ({self.filled_quantity}) cannot exceed execution_quantity ({self.execution_quantity})"
            )

        expected_remaining = self.execution_quantity - self.filled_quantity
        if self.remaining_quantity != expected_remaining:
            raise ValueError(
                f"remaining_quantity mismatch: expected {expected_remaining}, got {self.remaining_quantity}"
            )

        if math.isnan(self.average_fill_price) or math.isinf(self.average_fill_price) or self.average_fill_price < 0:
            raise ValueError(f"average_fill_price must be non-negative float, got {self.average_fill_price}")

    @property
    def requires_reconciliation(self) -> bool:
        """Invariant E9: Status UNKNOWN requires mandatory reconciliation before any retry."""
        return self.status == ExecutionStatus.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        """Convert ExecutionResult to dictionary representation."""
        return {
            "execution_id": self.execution_id,
            "execution_request_id": self.execution_request_id,
            "risk_decision_id": self.risk_decision_id,
            "broker_order_id": self.broker_order_id,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "requested_quantity": self.requested_quantity,
            "execution_quantity": self.execution_quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "rejection_reason": self.rejection_reason,
            "timestamp": self.timestamp.isoformat(),
        }
