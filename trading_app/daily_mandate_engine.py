"""
NexTrade Daily Trading Mandate Engine & Invariant U5 Enforcer.

Generates versioned, immutable Daily Trading Mandates defining capital ceilings, max loss, max risk,
trading windows, and protection policies. Enforces Invariant U5 (Autonomous Mandate Boundary) and
manages the Mandate State Machine and Trace Chain.
"""

import uuid
import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("DailyMandateEngine")


class MandateState(Enum if 'Enum' in globals() else object):
    pass

from enum import Enum, auto


class MandateState(Enum):
    MANDATE_CREATED = "MANDATE_CREATED"
    AWAITING_USER_APPROVAL = "AWAITING_USER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTONOMOUS_ENGINE_ARMED = "AUTONOMOUS_ENGINE_ARMED"
    AUTONOMOUS_TRADING_ACTIVE = "AUTONOMOUS_TRADING_ACTIVE"
    PAUSED = "PAUSED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    TRADING_WINDOW_CLOSED = "TRADING_WINDOW_CLOSED"
    FORCE_EXIT = "FORCE_EXIT"
    RECONCILIATION = "RECONCILIATION"
    EOD_REPORT_GENERATED = "EOD_REPORT_GENERATED"
    MANDATE_EXPIRED = "MANDATE_EXPIRED"


class U5MandateViolationException(Exception):
    """Raised when an autonomous action is attempted without an approved, immutable Daily Mandate."""
    pass


@dataclass
class MandateLimits:
    capital_available: float = 100000.0
    capital_deployed_limit: float = 50000.0
    max_risk_ceiling: float = 2000.0
    daily_loss_limit: float = 2500.0
    max_trades: int = 3
    max_concurrent_positions: int = 2
    trading_window_start: str = "09:30 IST"
    trading_window_end: str = "14:45 IST"
    stop_loss_mandatory: bool = True
    trailing_stop_enabled: bool = True
    auto_exit_enabled: bool = True
    force_market_close_exit: bool = True


@dataclass
class MandateTraceChain:
    mandate_id: str
    trade_plan_id: Optional[str] = None
    risk_decision_id: Optional[str] = None
    authorization_id: Optional[str] = None
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    protection_policy_id: Optional[str] = None
    exit_decision_id: Optional[str] = None
    reconciliation_id: Optional[str] = None

    def generate_full_audit_string(self) -> str:
        return f"{self.mandate_id} -> {self.trade_plan_id} -> {self.risk_decision_id} -> {self.authorization_id} -> {self.order_id} -> {self.position_id} -> {self.protection_policy_id} -> {self.exit_decision_id} -> {self.reconciliation_id}"


@dataclass
class DailyMandate:
    mandate_id: str
    mandate_version: int
    trading_date: str
    created_timestamp: str
    expiry_timestamp: str
    market_regime: str
    recommended_strategy_id: str
    recommended_strategy_name: str
    suitability_score: int
    recommendation_rationale: List[str]
    limits: MandateLimits
    state: MandateState = MandateState.AWAITING_USER_APPROVAL
    approved_by: Optional[str] = None
    approved_timestamp: Optional[str] = None
    mandate_hash: str = ""

    def compute_mandate_hash(self) -> str:
        payload = {
            "mandate_id": self.mandate_id,
            "mandate_version": self.mandate_version,
            "trading_date": self.trading_date,
            "market_regime": self.market_regime,
            "strategy": self.recommended_strategy_name,
            "capital_deployed": self.limits.capital_deployed_limit,
            "max_risk": self.limits.max_risk_ceiling,
            "daily_loss_limit": self.limits.daily_loss_limit
        }
        raw_json = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


class DailyMandateManager:
    """Manages creation, approval, and U5 boundary enforcement for Daily Mandates."""

    def __init__(self):
        self._current_mandate: Optional[DailyMandate] = None
        self._mandate_history: Dict[str, DailyMandate] = {}

    def create_daily_mandate(
        self,
        market_regime_label: str,
        recommended_strategy_id: str,
        recommended_strategy_name: str,
        suitability_score: int,
        primary_rationale: List[str],
        limits: Optional[MandateLimits] = None
    ) -> DailyMandate:
        today_str = datetime.now().strftime("%Y-%m-%d")
        mandate_id = f"mnd_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        lim = limits or MandateLimits()

        mandate = DailyMandate(
            mandate_id=mandate_id,
            mandate_version=1,
            trading_date=today_str,
            created_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            expiry_timestamp=f"{today_str} 15:30:00",
            market_regime=market_regime_label,
            recommended_strategy_id=recommended_strategy_id,
            recommended_strategy_name=recommended_strategy_name,
            suitability_score=suitability_score,
            recommendation_rationale=primary_rationale,
            limits=lim,
            state=MandateState.AWAITING_USER_APPROVAL
        )
        mandate.mandate_hash = mandate.compute_mandate_hash()
        self._current_mandate = mandate
        self._mandate_history[mandate_id] = mandate
        logger.info("Created Daily Mandate %s for strategy %s", mandate_id, recommended_strategy_name)
        return mandate

    def approve_mandate(self, mandate_id: str, user_id: str = "User_Corporate_Exec") -> DailyMandate:
        mandate = self.get_mandate(mandate_id)
        if not mandate:
            raise ValueError(f"Mandate ID {mandate_id} not found.")

        mandate.state = MandateState.APPROVED
        mandate.approved_by = user_id
        mandate.approved_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mandate.state = MandateState.AUTONOMOUS_TRADING_ACTIVE
        logger.info("Mandate %s APPROVED by %s. Status set to AUTONOMOUS_TRADING_ACTIVE", mandate_id, user_id)
        return mandate

    def pause_mandate(self, mandate_id: str, reason: str = "Paused by user") -> DailyMandate:
        mandate = self.get_mandate(mandate_id)
        if mandate and mandate.state == MandateState.AUTONOMOUS_TRADING_ACTIVE:
            mandate.state = MandateState.PAUSED
            logger.warning("Mandate %s PAUSED: %s", mandate_id, reason)
        return mandate

    def emergency_stop(self, mandate_id: str, reason: str = "Emergency Stop Triggered") -> DailyMandate:
        mandate = self.get_mandate(mandate_id)
        if mandate:
            mandate.state = MandateState.SAFETY_STOPPED
            logger.critical("Mandate %s SAFETY_STOPPED: %s", mandate_id, reason)
        return mandate

    def verify_u5_autonomous_boundary(self, mandate_id: Optional[str] = None):
        """Enforces Invariant U5: Raises U5MandateViolationException if mandate is missing or unapproved."""
        mandate = self.get_mandate(mandate_id) if mandate_id else self._current_mandate
        if not mandate:
            msg = "INVARIANT U5 BREACH: No Daily Mandate exists for this session. Autonomous execution prohibited."
            logger.critical(msg)
            raise U5MandateViolationException(msg)

        if mandate.state not in (MandateState.APPROVED, MandateState.AUTONOMOUS_ENGINE_ARMED, MandateState.AUTONOMOUS_TRADING_ACTIVE):
            msg = f"INVARIANT U5 BREACH: Mandate {mandate.mandate_id} is in state {mandate.state.value}. Execution requires explicit APPROVED state."
            logger.critical(msg)
            raise U5MandateViolationException(msg)

        return True

    def create_trace_chain(self, mandate_id: str) -> MandateTraceChain:
        return MandateTraceChain(mandate_id=mandate_id)

    def get_mandate(self, mandate_id: str) -> Optional[DailyMandate]:
        if self._current_mandate and self._current_mandate.mandate_id == mandate_id:
            return self._current_mandate
        return self._mandate_history.get(mandate_id)

    def get_current_mandate(self) -> Optional[DailyMandate]:
        return self._current_mandate
