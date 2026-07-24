# risk/kill_switch.py
"""
Canonical Multi-Level System Kill Switch & Circuit Breaker Engine for NexTrade.
Provides unbypassable safety gates, canonical precedence resolution,
atomic persistence with fail-closed recovery, and audit tracking.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import json
import os
import threading
from typing import Optional, Dict, Any, Tuple, Set, Mapping

from types import MappingProxyType

from contracts.order import OrderSide
from contracts.risk import OrderIntent, RiskRuleSeverity

SCHEMA_VERSION = 1


class KillSwitchLevel(str, Enum):
    GLOBAL = "GLOBAL"
    BROKER = "BROKER"
    STRATEGY = "STRATEGY"
    SYMBOL = "SYMBOL"


class CircuitBreakerType(str, Enum):
    SYSTEM_HEALTH = "SYSTEM_HEALTH"
    STALE_DATA = "STALE_DATA"
    DAILY_LOSS = "DAILY_LOSS"
    CONSECUTIVE_LOSS = "CONSECUTIVE_LOSS"


@dataclass(frozen=True)
class ScopeAuditRecord:
    """
    Audit tracking record for a kill switch or circuit breaker scope.
    """
    triggered_at: Optional[str] = None
    trigger_reason: Optional[str] = None
    trigger_source: Optional[str] = None
    reset_at: Optional[str] = None
    reset_reason: Optional[str] = None
    reset_source: Optional[str] = None


@dataclass(frozen=True)
class KillSwitchCheckResult:
    """
    Immutable output of Kill Switch evaluation.
    """
    is_blocked: bool
    candidate_quantity: int
    authorized_quantity: int                             # Q_2D <= Q_2C
    blocking_level: Optional[KillSwitchLevel] = None
    breaker_type: Optional[CircuitBreakerType] = None
    reason: Optional[str] = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.metrics, dict):
            object.__setattr__(self, 'metrics', MappingProxyType(dict(self.metrics)))


class KillSwitchManager:
    """
    Thread-safe Multi-Level Kill Switch and Circuit Breaker State Machine.
    """

    def __init__(
        self,
        state_file_path: str = "logs/kill_switch_state.json",
        stale_data_thresholds: Optional[Dict[Tuple[str, str], Decimal]] = None
    ):
        self._state_file_path = state_file_path
        self._stale_data_thresholds = stale_data_thresholds or {("NSE", "1m"): Decimal("30.0")}
        self._lock = threading.RLock()
        self._broker_health: Dict[str, bool] = {}

        # Internal State Storage
        self._global_active: bool = False
        self._global_audit: Optional[ScopeAuditRecord] = None

        self._brokers_active: Dict[str, ScopeAuditRecord] = {}
        self._strategies_active: Dict[str, ScopeAuditRecord] = {}
        self._symbols_active: Dict[str, ScopeAuditRecord] = {}
        self._breakers_active: Dict[CircuitBreakerType, ScopeAuditRecord] = {}

        self._load_state()

    def set_broker_health(self, broker_name: str, is_available: bool) -> None:
        """Update live execution connectivity for a broker adapter."""
        with self._lock:
            self._broker_health[broker_name] = is_available

    def evaluate_kill_switch(
        self,
        strategy_id: str,
        symbol: str,
        broker_name: str,
        order_intent: OrderIntent,
        candidate_quantity: int
    ) -> KillSwitchCheckResult:
        """
        Evaluate candidate order quantity against precedence hierarchy and broker availability.
        """
        with self._lock:
            # 1. Execution Availability Gate (Checked for ALL intents including EXIT/REDUCE)
            is_broker_available = self._broker_health.get(broker_name, True)
            if not is_broker_available:
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    blocking_level=KillSwitchLevel.BROKER,
                    reason=f"Broker '{broker_name}' execution feed is unavailable"
                )

            # 2. Risk Policy Gate for Risk-Reducing Intents (EXIT / REDUCE permitted)
            if order_intent in (OrderIntent.EXIT, OrderIntent.REDUCE):
                return KillSwitchCheckResult(
                    is_blocked=False,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=candidate_quantity,
                    reason="Risk-reducing order permitted by safety policy"
                )

            # 3. Risk Policy Gate Precedence Hierarchy for Risk-Increasing Intents (ENTRY / REVERSAL)
            # Priority 1: GLOBAL
            if self._global_active:
                reason = self._global_audit.trigger_reason if self._global_audit else "GLOBAL kill switch active"
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    blocking_level=KillSwitchLevel.GLOBAL,
                    reason=f"GLOBAL kill switch active: {reason}"
                )

            # Priority 2: BROKER
            if broker_name in self._brokers_active:
                audit = self._brokers_active[broker_name]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    blocking_level=KillSwitchLevel.BROKER,
                    reason=f"Broker '{broker_name}' kill switch active: {audit.trigger_reason}"
                )

            # Priority 3: STRATEGY
            if strategy_id in self._strategies_active:
                audit = self._strategies_active[strategy_id]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    blocking_level=KillSwitchLevel.STRATEGY,
                    reason=f"Strategy '{strategy_id}' kill switch active: {audit.trigger_reason}"
                )

            # Priority 4: SYMBOL
            if symbol in self._symbols_active:
                audit = self._symbols_active[symbol]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    blocking_level=KillSwitchLevel.SYMBOL,
                    reason=f"Symbol '{symbol}' kill switch active: {audit.trigger_reason}"
                )

            # Priority 5: SYSTEM_HEALTH Breaker
            if CircuitBreakerType.SYSTEM_HEALTH in self._breakers_active:
                audit = self._breakers_active[CircuitBreakerType.SYSTEM_HEALTH]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    breaker_type=CircuitBreakerType.SYSTEM_HEALTH,
                    reason=f"System health circuit breaker active: {audit.trigger_reason}"
                )

            # Priority 6: STALE_DATA Breaker
            if CircuitBreakerType.STALE_DATA in self._breakers_active:
                audit = self._breakers_active[CircuitBreakerType.STALE_DATA]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    breaker_type=CircuitBreakerType.STALE_DATA,
                    reason=f"Stale market data circuit breaker active: {audit.trigger_reason}"
                )

            # Priority 7: DAILY_LOSS Breaker
            if CircuitBreakerType.DAILY_LOSS in self._breakers_active:
                audit = self._breakers_active[CircuitBreakerType.DAILY_LOSS]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    breaker_type=CircuitBreakerType.DAILY_LOSS,
                    reason=f"Daily loss circuit breaker active: {audit.trigger_reason}"
                )

            # Priority 8: CONSECUTIVE_LOSS Breaker
            if CircuitBreakerType.CONSECUTIVE_LOSS in self._breakers_active:
                audit = self._breakers_active[CircuitBreakerType.CONSECUTIVE_LOSS]
                return KillSwitchCheckResult(
                    is_blocked=True,
                    candidate_quantity=candidate_quantity,
                    authorized_quantity=0,
                    breaker_type=CircuitBreakerType.CONSECUTIVE_LOSS,
                    reason=f"Consecutive loss circuit breaker active: {audit.trigger_reason}"
                )

            # All Safety Gates Passed
            return KillSwitchCheckResult(
                is_blocked=False,
                candidate_quantity=candidate_quantity,
                authorized_quantity=candidate_quantity,
                reason="All safety gates passed"
            )

    def check_stale_data(
        self,
        feed: str,
        timeframe: str,
        last_updated_time: datetime,
        now: Optional[datetime] = None
    ) -> bool:
        """
        Check if market data feed/timeframe is stale based on configured thresholds.
        Auto-trips STALE_DATA circuit breaker if age exceeds threshold.
        """
        with self._lock:
            if now is None:
                now = datetime.now(timezone.utc)

            threshold_sec = self._stale_data_thresholds.get((feed, timeframe), Decimal("30.0"))
            age_sec = Decimal(str((now - last_updated_time).total_seconds()))

            if age_sec >= threshold_sec:
                self.trigger_circuit_breaker(
                    CircuitBreakerType.STALE_DATA,
                    reason=f"Stale market data on feed '{feed}' timeframe '{timeframe}' (age: {age_sec:.1f}s >= threshold: {threshold_sec:.1f}s)",
                    source="STALE_DATA_MONITOR"
                )
                return True
            return False

    # ----------------------------------------------------------------------
    # Trigger Operations
    # ----------------------------------------------------------------------

    def trigger_global(self, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._global_active = True
            self._global_audit = ScopeAuditRecord(triggered_at=now_iso, trigger_reason=reason, trigger_source=source)
            self._save_state()

    def trigger_broker(self, broker_name: str, reason: str, source: str = "SYSTEM_HEALTH") -> None:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._brokers_active[broker_name] = ScopeAuditRecord(triggered_at=now_iso, trigger_reason=reason, trigger_source=source)
            self._save_state()

    def trigger_strategy(self, strategy_id: str, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._strategies_active[strategy_id] = ScopeAuditRecord(triggered_at=now_iso, trigger_reason=reason, trigger_source=source)
            self._save_state()

    def trigger_symbol(self, symbol: str, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._symbols_active[symbol] = ScopeAuditRecord(triggered_at=now_iso, trigger_reason=reason, trigger_source=source)
            self._save_state()

    def trigger_circuit_breaker(self, breaker_type: CircuitBreakerType, reason: str, source: str = "SYSTEM") -> None:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._breakers_active[breaker_type] = ScopeAuditRecord(triggered_at=now_iso, trigger_reason=reason, trigger_source=source)
            self._save_state()

    # ----------------------------------------------------------------------
    # Strict Individual Reset Operations
    # ----------------------------------------------------------------------
    def reset_global(self, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            self._global_active = False
            now_iso = datetime.now(timezone.utc).isoformat()
            if self._global_audit:
                self._global_audit = ScopeAuditRecord(
                    triggered_at=self._global_audit.triggered_at,
                    trigger_reason=self._global_audit.trigger_reason,
                    trigger_source=self._global_audit.trigger_source,
                    reset_at=now_iso,
                    reset_reason=reason,
                    reset_source=source
                )
            self._save_state()

    def reset_broker(self, broker_name: str, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            self._brokers_active.pop(broker_name, None)
            self._save_state()

    def reset_strategy(self, strategy_id: str, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            self._strategies_active.pop(strategy_id, None)
            self._save_state()

    def reset_symbol(self, symbol: str, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            self._symbols_active.pop(symbol, None)
            self._save_state()

    def reset_circuit_breaker(self, breaker_type: CircuitBreakerType, reason: str, source: str = "OPERATOR") -> None:
        with self._lock:
            self._breakers_active.pop(breaker_type, None)
            self._save_state()

    # ----------------------------------------------------------------------
    # Atomic Persistence & Safe Fail-Closed State Recovery
    # ----------------------------------------------------------------------
    def _save_state(self) -> None:
        """Save state to file using atomic tmp write -> fsync -> os.replace."""
        data = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "global_active": self._global_active,
            "global_audit": self._audit_to_dict(self._global_audit),
            "brokers": {k: self._audit_to_dict(v) for k, v in self._brokers_active.items()},
            "strategies": {k: self._audit_to_dict(v) for k, v in self._strategies_active.items()},
            "symbols": {k: self._audit_to_dict(v) for k, v in self._symbols_active.items()},
            "circuit_breakers": {k.value: self._audit_to_dict(v) for k, v in self._breakers_active.items()},
        }

        os.makedirs(os.path.dirname(os.path.abspath(self._state_file_path)), exist_ok=True)
        tmp_path = f"{self._state_file_path}.tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, self._state_file_path)

    def _load_state(self) -> None:
        """Load state from file; fail closed into GLOBAL block if corrupt/invalid."""
        if not os.path.exists(self._state_file_path):
            return

        try:
            with open(self._state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(f"Unsupported schema version: {data.get('schema_version')}")

            self._global_active = data.get("global_active", False)
            self._global_audit = self._audit_from_dict(data.get("global_audit"))

            self._brokers_active = {k: self._audit_from_dict(v) for k, v in data.get("brokers", {}).items()}
            self._strategies_active = {k: self._audit_from_dict(v) for k, v in data.get("strategies", {}).items()}
            self._symbols_active = {k: self._audit_from_dict(v) for k, v in data.get("symbols", {}).items()}

            self._breakers_active = {}
            for b_key, b_audit in data.get("circuit_breakers", {}).items():
                self._breakers_active[CircuitBreakerType(b_key)] = self._audit_from_dict(b_audit)

        except Exception as e:
            # FAIL-CLOSED into GLOBAL block upon corruption or schema error
            self._global_active = True
            now_iso = datetime.now(timezone.utc).isoformat()
            self._global_audit = ScopeAuditRecord(
                triggered_at=now_iso,
                trigger_reason=f"STATE_PERSISTENCE_FAILURE: {str(e)}",
                trigger_source="SAFETY_RECOVERY"
            )

    @staticmethod
    def _audit_to_dict(rec: Optional[ScopeAuditRecord]) -> Optional[Dict[str, Any]]:
        if rec is None:
            return None
        return {
            "triggered_at": rec.triggered_at,
            "trigger_reason": rec.trigger_reason,
            "trigger_source": rec.trigger_source,
            "reset_at": rec.reset_at,
            "reset_reason": rec.reset_reason,
            "reset_source": rec.reset_source,
        }

    @staticmethod
    def _audit_from_dict(d: Optional[Dict[str, Any]]) -> Optional[ScopeAuditRecord]:
        if not d:
            return None
        return ScopeAuditRecord(
            triggered_at=d.get("triggered_at"),
            trigger_reason=d.get("trigger_reason"),
            trigger_source=d.get("trigger_source"),
            reset_at=d.get("reset_at"),
            reset_reason=d.get("reset_reason"),
            reset_source=d.get("reset_source"),
        )
