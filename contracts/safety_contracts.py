# contracts/safety_contracts.py
"""
Canonical Safety Contracts & Domain Models for NexTrade (Sub-Phase 4D).
Defines strongly typed, frozen models for LiveSafetyGate evaluations,
fail-closed barrier results, safety contexts, and multi-factor safety unlocks.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional


class SafetyBarrierStatus(str, Enum):
    PASS = "PASS"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class ExecutionEnvironment(str, Enum):
    PAPER = "PAPER"
    SANDBOX = "SANDBOX"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class OrderIntent(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"


@dataclass(frozen=True)
class SafetyBarrierResult:
    """Evaluation result for an individual fail-closed safety barrier."""
    barrier_id: str
    barrier_name: str
    status: SafetyBarrierStatus
    reason: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class MultiFactorUnlock:
    """Operator authentication token container for unlocking live trading."""
    operator_token: str
    unlocked_at: datetime
    expires_at: datetime
    unlocked_by: str

    def is_valid(self, now: Optional[datetime] = None) -> bool:
        """Returns True if token is non-empty and unexpired."""
        current_time = now or datetime.now(timezone.utc)
        if not self.operator_token or not self.unlocked_by:
            return False
        return current_time < self.expires_at


@dataclass(frozen=True)
class LiveSafetyLimits:
    """Configurable safety thresholds and exposure caps."""
    max_order_notional: float = 50000.0
    max_position_exposure: float = 100000.0
    max_daily_loss: float = 5000.0
    max_open_orders: int = 20
    max_orders_per_minute: int = 60


@dataclass(frozen=True)
class SafetyEvaluationContext:
    """
    Immutable, strongly-typed state snapshot supplied to LiveSafetyGate for evaluation.
    Enforces strict age checking via max_state_age_seconds.
    """
    live_trading_enabled: bool = False
    environment: ExecutionEnvironment = ExecutionEnvironment.PAPER
    order_intent: OrderIntent = OrderIntent.ENTRY
    multi_factor_unlock: Optional[MultiFactorUnlock] = None
    kill_switch_mode: str = "NORMAL"  # NORMAL, REDUCE_ONLY, HARD_HALT
    daily_loss: float = 0.0
    current_position_exposure: float = 0.0
    projected_position_exposure: float = 0.0
    active_open_orders: int = 0
    broker_credentials_status: str = "VALID"
    broker_connection_status: str = "CONNECTED"
    audit_logger_status: str = "OK"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    max_state_age_seconds: float = 5.0

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        """Returns True if context timestamp is older than max_state_age_seconds."""
        current_time = now or datetime.now(timezone.utc)
        age = (current_time - self.timestamp).total_seconds()
        return age > self.max_state_age_seconds or age < -1.0


@dataclass(frozen=True)
class SafetyEvaluationResult:
    """Aggregated evaluation result returned by LiveSafetyGate."""
    is_authorized: bool
    barrier_results: List[SafetyBarrierResult]
    denial_reasons: List[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
