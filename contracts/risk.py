# contracts/risk.py
"""
Canonical Risk Contract Specifications for NexTrade.
Defines risk decision enums, immutable check results, risk decisions,
limits configuration, and immutable point-in-time risk context snapshots.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple, Mapping
from types import MappingProxyType

from contracts.order import Order, OrderSide
from contracts.position import Position
from contracts.funds import FundsInfo


class OrderIntent(str, Enum):
    """
    Dimensional intent of an order relative to existing portfolio position.
    """
    ENTRY = "ENTRY"          # Opens new risk exposure
    EXIT = "EXIT"            # Closes open position completely (Allowed under Kill Switch)
    REDUCE = "REDUCE"        # Lowers existing position size (Allowed under Kill Switch)
    REVERSAL = "REVERSAL"    # Flips position side (e.g. Long -> Short); treated as new risk exposure


class RiskDecisionStatus(str, Enum):
    """
    Execution status resulting from Risk Engine evaluation.
    """
    APPROVED = "APPROVED"                # Full requested quantity authorized
    MODIFIED = "MODIFIED"                # Partial quantity authorized (0 < approved < requested)
    REJECTED = "REJECTED"                # Order rejected due to risk limit breach
    BLOCKED_BY_KILL_SWITCH = "BLOCKED"   # Order blocked by active hard safety gate


class RiskRuleCategory(str, Enum):
    """
    Category of the evaluated risk rule.
    """
    KILL_SWITCH = "KILL_SWITCH"
    POSITION_SIZING = "POSITION_SIZING"
    ACCOUNT = "ACCOUNT"
    PORTFOLIO = "PORTFOLIO"
    EXPOSURE = "EXPOSURE"
    DAILY_LOSS = "DAILY_LOSS"
    LIQUIDITY = "LIQUIDITY"
    BROKER = "BROKER"


class RiskRuleSeverity(str, Enum):
    """
    Severity level of a risk check result.
    """
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


@dataclass(frozen=True)
class RiskCheckResult:
    """
    Immutable evaluation result of a single risk rule check.
    """
    rule_name: str
    category: RiskRuleCategory
    passed: bool
    severity: RiskRuleSeverity
    reason: Optional[str] = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.metrics, dict):
            object.__setattr__(self, 'metrics', MappingProxyType(dict(self.metrics)))

    def to_dict(self) -> Dict[str, Any]:
        """Convert RiskCheckResult to dictionary."""
        return {
            "rule_name": self.rule_name,
            "category": self.category.value,
            "passed": self.passed,
            "severity": self.severity.value,
            "reason": self.reason,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskCheckResult":
        """Instantiate RiskCheckResult from dictionary."""
        return cls(
            rule_name=data["rule_name"],
            category=RiskRuleCategory(data["category"]),
            passed=bool(data["passed"]),
            severity=RiskRuleSeverity(data["severity"]),
            reason=data.get("reason"),
            metrics=data.get("metrics", {}),
        )


@dataclass(frozen=True)
class RiskDecision:
    """
    Immutable authorized risk decision output for an order request.
    """
    decision_id: str
    signal_id: Optional[str]
    order_intent: OrderIntent
    decision: RiskDecisionStatus
    requested_quantity: int
    approved_quantity: int
    modification_reason: Optional[str] = None
    checks_evaluated: Tuple[RiskCheckResult, ...] = field(default_factory=tuple)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, 'timestamp', self.timestamp.replace(tzinfo=timezone.utc))

        if isinstance(self.checks_evaluated, list):
            object.__setattr__(self, 'checks_evaluated', tuple(self.checks_evaluated))

        # Enforce contract invariants
        if self.requested_quantity < 0:
            raise ValueError(f"requested_quantity must be non-negative, got {self.requested_quantity}")
        if self.approved_quantity < 0:
            raise ValueError(f"approved_quantity must be non-negative, got {self.approved_quantity}")
        if self.approved_quantity > self.requested_quantity:
            raise ValueError(
                f"approved_quantity ({self.approved_quantity}) cannot exceed requested_quantity ({self.requested_quantity})"
            )

        if self.decision == RiskDecisionStatus.MODIFIED:
            if not (0 < self.approved_quantity < self.requested_quantity):
                raise ValueError(
                    f"MODIFIED status requires 0 < approved_quantity ({self.approved_quantity}) < requested_quantity ({self.requested_quantity})"
                )

        if self.decision in (RiskDecisionStatus.REJECTED, RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH):
            if self.approved_quantity != 0:
                raise ValueError(f"REJECTED/BLOCKED decision requires approved_quantity == 0, got {self.approved_quantity}")

    @property
    def is_submittable(self) -> bool:
        """Core execution invariant: Order may only be submitted if approved/modified with quantity > 0."""
        return self.decision in (RiskDecisionStatus.APPROVED, RiskDecisionStatus.MODIFIED) and self.approved_quantity > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert RiskDecision to dictionary representation."""
        return {
            "decision_id": self.decision_id,
            "signal_id": self.signal_id,
            "order_intent": self.order_intent.value,
            "decision": self.decision.value,
            "requested_quantity": self.requested_quantity,
            "approved_quantity": self.approved_quantity,
            "modification_reason": self.modification_reason,
            "checks_evaluated": [c.to_dict() for c in self.checks_evaluated],
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskDecision":
        """Instantiate RiskDecision from dictionary."""
        return cls(
            decision_id=data["decision_id"],
            signal_id=data.get("signal_id"),
            order_intent=OrderIntent(data["order_intent"]),
            decision=RiskDecisionStatus(data["decision"]),
            requested_quantity=int(data["requested_quantity"]),
            approved_quantity=int(data["approved_quantity"]),
            modification_reason=data.get("modification_reason"),
            checks_evaluated=tuple(RiskCheckResult.from_dict(c) for c in data.get("checks_evaluated", [])),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class RiskLimits:
    """
    Immutable risk limits configuration.
    """
    min_risk_per_trade_pct: float = 0.25
    default_risk_per_trade_pct: float = 0.50       # Default 0.50%
    max_risk_per_trade_pct: float = 1.00
    max_daily_loss_amount: float = 5000.0
    max_open_positions: int = 5
    max_symbol_exposure_pct: float = 20.0
    max_sector_exposure_pct: float = 40.0

    def __post_init__(self):
        if not (0.0 < self.min_risk_per_trade_pct <= self.default_risk_per_trade_pct <= self.max_risk_per_trade_pct):
            raise ValueError(
                f"Invalid risk bounds: min ({self.min_risk_per_trade_pct}) <= default ({self.default_risk_per_trade_pct}) <= max ({self.max_risk_per_trade_pct})"
            )


@dataclass(frozen=True)
class RiskContext:
    """
    Immutable point-in-time snapshot of account and portfolio state used for risk evaluation.
    """
    funds: FundsInfo
    open_positions: Tuple[Position, ...] = field(default_factory=tuple)
    open_orders: Tuple[Order, ...] = field(default_factory=tuple)
    daily_realized_pnl: float = 0.0
    daily_unrealized_pnl: float = 0.0
    active_kill_switches: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.open_positions, list):
            object.__setattr__(self, 'open_positions', tuple(self.open_positions))
        if isinstance(self.open_orders, list):
            object.__setattr__(self, 'open_orders', tuple(self.open_orders))
        if isinstance(self.active_kill_switches, dict):
            object.__setattr__(self, 'active_kill_switches', MappingProxyType(dict(self.active_kill_switches)))
