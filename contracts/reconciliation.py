# contracts/reconciliation.py
"""
Canonical Reconciliation Domain Contracts for NexTrade (Sub-Phase 3E).
Defines immutable contracts for ReconciliationStatus, DiscrepancySeverity,
ReconciliationDiscrepancy, ReconciliationRequest, ReconciliationResult, and ReconciliationAuditRecord.
Enforces Invariants E29 - E33.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import math
from typing import Optional, Dict, Any, List, Tuple

from contracts.execution import ExecutionStatus


class ReconciliationStatus(str, Enum):
    """Status of reconciliation processing."""
    PENDING = "PENDING"
    RESOLVED_FILLED = "RESOLVED_FILLED"
    RESOLVED_PARTIAL = "RESOLVED_PARTIAL"
    RESOLVED_REJECTED = "RESOLVED_REJECTED"
    RESOLVED_CANCELLED = "RESOLVED_CANCELLED"
    UNRESOLVED_ESCALATION = "UNRESOLVED_ESCALATION"


class DiscrepancySeverity(str, Enum):
    """Severity classification for detected discrepancies."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class DiscrepancyType(str, Enum):
    """Types of reconciliation discrepancies."""
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRICE_SLIPPAGE = "PRICE_SLIPPAGE"
    UNMATCHED_ORDER = "UNMATCHED_ORDER"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    CUMULATIVE_FILL_REGRESSION = "CUMULATIVE_FILL_REGRESSION"


@dataclass(frozen=True)
class ReconciliationDiscrepancy:
    """
    Immutable record of a detected reconciliation discrepancy (Invariant E32).
    """
    discrepancy_type: DiscrepancyType
    expected_value: Any
    actual_value: Any
    severity: DiscrepancySeverity
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discrepancy_type": self.discrepancy_type.value if isinstance(self.discrepancy_type, Enum) else str(self.discrepancy_type),
            "expected_value": str(self.expected_value),
            "actual_value": str(self.actual_value),
            "severity": self.severity.value if isinstance(self.severity, Enum) else str(self.severity),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class ReconciliationRequest:
    """
    Immutable request payload for order or position reconciliation.
    """
    reconciliation_request_id: str
    execution_request_id: str
    broker_order_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    symbol: Optional[str] = None
    position_id: Optional[str] = None
    reason: str = "MANUAL_OR_UNKNOWN_STATE"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.reconciliation_request_id:
            raise ValueError("reconciliation_request_id must be a non-empty string")
        if not self.execution_request_id:
            raise ValueError("execution_request_id must be a non-empty string")
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reconciliation_request_id": self.reconciliation_request_id,
            "execution_request_id": self.execution_request_id,
            "broker_order_id": self.broker_order_id,
            "idempotency_key": self.idempotency_key,
            "symbol": self.symbol,
            "position_id": self.position_id,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class ReconciliationResult:
    """
    Immutable result outcome of a reconciliation attempt (Invariants E31, E33).
    """
    reconciliation_id: str
    reconciliation_key: str
    execution_request_id: str
    broker_order_id: Optional[str]
    status: ReconciliationStatus
    resolved_execution_status: ExecutionStatus
    cumulative_filled_quantity: int
    fill_delta: int
    remaining_quantity: int
    average_fill_price: float
    discrepancies: List[ReconciliationDiscrepancy] = field(default_factory=list)
    details: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.reconciliation_id:
            raise ValueError("reconciliation_id must be a non-empty string")
        if not self.reconciliation_key:
            raise ValueError("reconciliation_key must be a non-empty string")
        if not self.execution_request_id:
            raise ValueError("execution_request_id must be a non-empty string")
        if self.cumulative_filled_quantity < 0:
            raise ValueError(f"cumulative_filled_quantity must be non-negative, got {self.cumulative_filled_quantity}")
        if self.fill_delta < 0:
            raise ValueError(f"fill_delta must be non-negative, got {self.fill_delta}")
        if self.remaining_quantity < 0:
            raise ValueError(f"remaining_quantity must be non-negative, got {self.remaining_quantity}")
        if math.isnan(self.average_fill_price) or math.isinf(self.average_fill_price) or self.average_fill_price < 0:
            raise ValueError(f"average_fill_price must be non-negative float, got {self.average_fill_price}")
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    @staticmethod
    def compute_reconciliation_key(
        broker_order_id: Optional[str],
        authoritative_status: ExecutionStatus,
        cumulative_filled_quantity: int,
        average_fill_price: float,
        broker_event_id: Optional[str] = None
    ) -> str:
        """
        Invariant E33: Compute deterministic reconciliation key from authoritative broker state.
        """
        raw = f"{broker_order_id or 'NONE'}:{authoritative_status.value}:{cumulative_filled_quantity}:{average_fill_price:.4f}:{broker_event_id or 'NONE'}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reconciliation_id": self.reconciliation_id,
            "reconciliation_key": self.reconciliation_key,
            "execution_request_id": self.execution_request_id,
            "broker_order_id": self.broker_order_id,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "resolved_execution_status": self.resolved_execution_status.value if isinstance(self.resolved_execution_status, Enum) else str(self.resolved_execution_status),
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "fill_delta": self.fill_delta,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class ReconciliationAuditRecord:
    """
    Immutable audit record for chain of custody in reconciliation actions.
    """
    audit_id: str
    reconciliation_id: str
    reconciliation_key: str
    execution_request_id: str
    previous_execution_status: ExecutionStatus
    new_execution_status: ExecutionStatus
    fill_delta: int
    cumulative_filled_quantity: int
    details: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "reconciliation_id": self.reconciliation_id,
            "reconciliation_key": self.reconciliation_key,
            "execution_request_id": self.execution_request_id,
            "previous_execution_status": self.previous_execution_status.value if isinstance(self.previous_execution_status, Enum) else str(self.previous_execution_status),
            "new_execution_status": self.new_execution_status.value if isinstance(self.new_execution_status, Enum) else str(self.new_execution_status),
            "fill_delta": self.fill_delta,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }
