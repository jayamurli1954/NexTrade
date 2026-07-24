# contracts/protection.py
"""
Canonical Protection & Exit Management Contracts for NexTrade.
Defines ProtectionPlan, TrailingDistanceType, ProtectionDecision, TrailingStopState,
and ProtectionAdjustmentEvent as first-class domain contracts.
Enforces Protection Invariants E17 - E23 for both paper and live trading.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Optional, Dict, Any, Tuple

from contracts.position import PositionSide


class ProtectionType(str, Enum):
    """Protection execution type."""
    FIXED_SL_TP = "FIXED_SL_TP"
    TRAILING_STOP = "TRAILING_STOP"
    DYNAMIC_TARGET = "DYNAMIC_TARGET"


class TrailingDistanceType(str, Enum):
    """Trailing distance calculation type."""
    ABSOLUTE = "ABSOLUTE"      # e.g. Absolute price distance ₹20.0
    PERCENTAGE = "PERCENTAGE"  # e.g. Percentage distance 2.0%


class ProtectionDecisionType(str, Enum):
    """Protection Engine evaluation outcome decision."""
    NO_ACTION = "NO_ACTION"
    UPDATE_TRAILING_STOP = "UPDATE_TRAILING_STOP"
    TRIGGER_STOP_LOSS = "TRIGGER_STOP_LOSS"
    TRIGGER_TAKE_PROFIT = "TRIGGER_TAKE_PROFIT"
    EXIT = "EXIT"


@dataclass(frozen=True)
class ProtectionPlan:
    """
    Canonical Immutable Protection Plan.
    Specifies Initial SL, Initial TP, Trailing Distance, Trailing Distance Type, Trailing Step, and Activation.
    """
    position_side: PositionSide
    entry_price: float
    initial_stop_loss: Optional[float] = None
    initial_take_profit: Optional[float] = None
    trailing_enabled: bool = False
    trailing_distance: Optional[float] = None
    trailing_distance_type: TrailingDistanceType = TrailingDistanceType.ABSOLUTE
    trailing_step: Optional[float] = None
    trailing_activation_price: Optional[float] = None

    def __post_init__(self):
        if math.isnan(self.entry_price) or math.isinf(self.entry_price) or self.entry_price <= 0:
            raise ValueError(f"entry_price must be a positive float, got {self.entry_price}")

        # Invariant E17: Stop-Loss Direction Integrity
        if self.initial_stop_loss is not None:
            if math.isnan(self.initial_stop_loss) or math.isinf(self.initial_stop_loss) or self.initial_stop_loss <= 0:
                raise ValueError(f"initial_stop_loss must be positive float, got {self.initial_stop_loss}")

            if self.position_side == PositionSide.LONG and self.initial_stop_loss >= self.entry_price:
                raise ValueError(
                    f"Invariant E17 Breached (LONG): initial_stop_loss ({self.initial_stop_loss}) "
                    f"must be strictly less than entry_price ({self.entry_price})"
                )
            elif self.position_side == PositionSide.SHORT and self.initial_stop_loss <= self.entry_price:
                raise ValueError(
                    f"Invariant E17 Breached (SHORT): initial_stop_loss ({self.initial_stop_loss}) "
                    f"must be strictly greater than entry_price ({self.entry_price})"
                )

        # Invariant E18: Target Direction Integrity
        if self.initial_take_profit is not None:
            if math.isnan(self.initial_take_profit) or math.isinf(self.initial_take_profit) or self.initial_take_profit <= 0:
                raise ValueError(f"initial_take_profit must be positive float, got {self.initial_take_profit}")

            if self.position_side == PositionSide.LONG and self.initial_take_profit <= self.entry_price:
                raise ValueError(
                    f"Invariant E18 Breached (LONG): initial_take_profit ({self.initial_take_profit}) "
                    f"must be strictly greater than entry_price ({self.entry_price})"
                )
            elif self.position_side == PositionSide.SHORT and self.initial_take_profit >= self.entry_price:
                raise ValueError(
                    f"Invariant E18 Breached (SHORT): initial_take_profit ({self.initial_take_profit}) "
                    f"must be strictly less than entry_price ({self.entry_price})"
                )

        # Trailing Stop Configuration Validation
        if self.trailing_enabled:
            if self.trailing_distance is None or self.trailing_distance <= 0:
                raise ValueError("trailing_distance must be a positive float when trailing_enabled is True")

            if self.trailing_step is None or self.trailing_step <= 0:
                raise ValueError("trailing_step must be a positive float when trailing_enabled is True")

    def to_dict(self) -> Dict[str, Any]:
        """Convert ProtectionPlan to dictionary representation."""
        return {
            "position_side": self.position_side.value if isinstance(self.position_side, Enum) else str(self.position_side),
            "entry_price": self.entry_price,
            "initial_stop_loss": self.initial_stop_loss,
            "initial_take_profit": self.initial_take_profit,
            "trailing_enabled": self.trailing_enabled,
            "trailing_distance": self.trailing_distance,
            "trailing_distance_type": self.trailing_distance_type.value if isinstance(self.trailing_distance_type, Enum) else str(self.trailing_distance_type),
            "trailing_step": self.trailing_step,
            "trailing_activation_price": self.trailing_activation_price,
        }


@dataclass(frozen=True)
class TrailingStopState:
    """
    Immutable State tracking active trailing stop progression.
    Stores last_reference_price to measure TrailingStep relative to last accepted reference price.
    Enforces Trailing Monotonicity (Invariant E19) and Step Integrity (Invariant E20).
    """
    position_side: PositionSide
    entry_price: float
    current_stop_loss: float
    trailing_distance: float
    trailing_distance_type: TrailingDistanceType
    trailing_step: float
    highest_favorable_price: float
    last_reference_price: float
    is_active: bool = True

    def calculate_update(self, current_market_price: float) -> Tuple[bool, "TrailingStopState"]:
        """
        Evaluate market price movement relative to last_reference_price.
        
        Rules:
        - LONG: Market Price ^ => Stop Loss ^ (Monotonically Non-Decreasing).
        - SHORT: Market Price v => Stop Loss v (Monotonically Non-Increasing).
        - Invariant E20: Update occurs ONLY IF |favorable_movement| >= trailing_step relative to last_reference_price.
        """
        if not self.is_active or current_market_price <= 0:
            return False, self

        if self.position_side == PositionSide.LONG:
            # Check for new highest price
            new_highest = max(self.highest_favorable_price, current_market_price)
            favorable_delta = new_highest - self.last_reference_price

            # Invariant E20: Step Integrity Check relative to last_reference_price
            if favorable_delta >= self.trailing_step:
                if self.trailing_distance_type == TrailingDistanceType.PERCENTAGE:
                    dist_value = new_highest * (self.trailing_distance / 100.0)
                else:
                    dist_value = self.trailing_distance

                calculated_sl = new_highest - dist_value
                
                # Invariant E19 & E21: Trailing Monotonicity (LONG SL can only increase)
                new_sl = max(self.current_stop_loss, calculated_sl)
                
                if new_sl > self.current_stop_loss:
                    updated_state = TrailingStopState(
                        position_side=self.position_side,
                        entry_price=self.entry_price,
                        current_stop_loss=new_sl,
                        trailing_distance=self.trailing_distance,
                        trailing_distance_type=self.trailing_distance_type,
                        trailing_step=self.trailing_step,
                        highest_favorable_price=new_highest,
                        last_reference_price=new_highest,
                        is_active=True
                    )
                    return True, updated_state

        elif self.position_side == PositionSide.SHORT:
            # Check for new lowest price
            new_lowest = min(self.highest_favorable_price, current_market_price)
            favorable_delta = self.last_reference_price - new_lowest

            # Invariant E20: Step Integrity Check relative to last_reference_price
            if favorable_delta >= self.trailing_step:
                if self.trailing_distance_type == TrailingDistanceType.PERCENTAGE:
                    dist_value = new_lowest * (self.trailing_distance / 100.0)
                else:
                    dist_value = self.trailing_distance

                calculated_sl = new_lowest + dist_value
                
                # Invariant E19 & E21: Trailing Monotonicity (SHORT SL can only decrease)
                new_sl = min(self.current_stop_loss, calculated_sl)
                
                if new_sl < self.current_stop_loss:
                    updated_state = TrailingStopState(
                        position_side=self.position_side,
                        entry_price=self.entry_price,
                        current_stop_loss=new_sl,
                        trailing_distance=self.trailing_distance,
                        trailing_distance_type=self.trailing_distance_type,
                        trailing_step=self.trailing_step,
                        highest_favorable_price=new_lowest,
                        last_reference_price=new_lowest,
                        is_active=True
                    )
                    return True, updated_state

        return False, self


@dataclass(frozen=True)
class ProtectionDecision:
    """
    Canonical Protection Decision produced by Protection Engine.
    Parallels RiskDecision structure: RiskEngine -> RiskDecision, ProtectionEngine -> ProtectionDecision.
    """
    decision: ProtectionDecisionType
    position_id: str
    symbol: str
    position_side: PositionSide
    trigger_price: float
    current_stop_loss: Optional[float] = None
    new_stop_loss: Optional[float] = None
    take_profit_price: Optional[float] = None
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))


@dataclass(frozen=True)
class ProtectionAdjustmentEvent:
    """
    Invariant E23: Immutable audit log event tracking every SL / TP / Trailing Stop update.
    """
    event_id: str
    execution_request_id: str
    risk_decision_id: str
    symbol: str
    position_side: PositionSide
    previous_stop_loss: float
    new_stop_loss: float
    trigger_market_price: float
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "event_id": self.event_id,
            "execution_request_id": self.execution_request_id,
            "risk_decision_id": self.risk_decision_id,
            "symbol": self.symbol,
            "position_side": self.position_side.value if isinstance(self.position_side, Enum) else str(self.position_side),
            "previous_stop_loss": self.previous_stop_loss,
            "new_stop_loss": self.new_stop_loss,
            "trigger_market_price": self.trigger_market_price,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }
