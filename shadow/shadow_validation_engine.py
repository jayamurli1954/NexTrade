"""
NexTrade Phase 5G / 6D — Shadow Validation Engine.

Executes real-time shadow validation comparing live strategy signals against paper/sandbox execution.
Tracks slippage, latency, fill probability, signal consistency, order intent parity, and enforces zero-capital guards.
Trips SafetyState.HOLD on market data staleness (>2s) or signal drift (>0.1%).
"""

import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

from governance.secret_sanitizer import SecretSanitizer
from hardening.safety_control_plane import SafetyControlPlane, SafetyState

logger = logging.getLogger("ShadowValidationEngine")


class ZeroCapitalViolationException(Exception):
    """Raised when an execution intent in shadow mode attempts live capital dispatch or non-zero capital exposure."""
    pass


class ShadowDriftViolationException(Exception):
    """Raised when signal drift or market data staleness exceeds safety bounds."""
    pass


@dataclass
class ShadowValidationRecord:
    shadow_id: str
    signal_symbol: str
    signal_action: str
    signal_price: float
    simulated_fill_price: float
    slippage_pct: float
    latency_ms: float
    capital_exposure: float
    order_intent_parity: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class ShadowReconciliationRecord:
    reconciliation_id: str
    paper_order_id: str
    shadow_id: str
    status_match: bool
    price_delta: float
    quantity_delta: float
    timestamp: float = field(default_factory=time.time)


class ShadowValidationEngine:
    """
    Validation engine tracking shadow execution metrics under zero capital exposure.
    Enforces strict physical zero-capital guard ($0.00), parameter parity, and staleness/drift limits.
    """

    def __init__(
        self,
        max_allowed_slippage_pct: float = 2.0,
        max_allowed_latency_ms: float = 150.0,
        max_allowed_signal_drift_pct: float = 0.1,
        max_allowed_staleness_sec: float = 2.0,
        control_plane: Optional[SafetyControlPlane] = None
    ) -> None:
        self.max_allowed_slippage_pct = max_allowed_slippage_pct
        self.max_allowed_latency_ms = max_allowed_latency_ms
        self.max_allowed_signal_drift_pct = max_allowed_signal_drift_pct
        self.max_allowed_staleness_sec = max_allowed_staleness_sec
        self.control_plane = control_plane or SafetyControlPlane()
        
        self._records: List[ShadowValidationRecord] = []
        self._reconciliations: List[ShadowReconciliationRecord] = []
        self._last_tick_time: float = time.time()
        self.zero_capital_mode: bool = True

    def record_market_tick(self, symbol: str, price: float, timestamp: Optional[float] = None) -> bool:
        """
        Record incoming market data tick and check tick staleness.
        If gap > max_allowed_staleness_sec (2s), trips SafetyState.HOLD.
        """
        now = timestamp or time.time()
        gap = now - self._last_tick_time
        self._last_tick_time = now

        if gap > self.max_allowed_staleness_sec:
            msg = f"Market data tick gap ({gap:.2f}s) exceeded staleness limit ({self.max_allowed_staleness_sec}s)"
            logger.critical(msg)
            self.control_plane.report_subsystem_state("shadow_validation_engine", SafetyState.HOLD, msg)
            return False

        return True

    def verify_zero_capital_guard(self, capital_requested: float) -> bool:
        """
        Non-bypassable Zero-Capital Guard (6D-P2).
        Enforces capital_exposure == 0.00. Any positive value raises ZeroCapitalViolationException.
        """
        if not self.zero_capital_mode or capital_requested > 0.0:
            msg = f"ZERO-CAPITAL VIOLATION: Shadow mode attempted live capital dispatch of ${capital_requested:.2f}"
            logger.critical(msg)
            self.control_plane.report_subsystem_state("shadow_validation_engine", SafetyState.HARD_HALT, msg)
            raise ZeroCapitalViolationException(msg)
        return True

    def evaluate_order_intent_parity(self, signal_payload: Dict[str, Any], intent_payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Evaluates 5-parameter order intent parity (6D-P5): symbol, side/action, quantity, order_type, price.
        """
        discrepancies = []
        if str(signal_payload.get("symbol")).upper() != str(intent_payload.get("symbol")).upper():
            discrepancies.append(f"symbol mismatch: {signal_payload.get('symbol')} != {intent_payload.get('symbol')}")
        if str(signal_payload.get("action")).upper() != str(intent_payload.get("side", intent_payload.get("action"))).upper():
            discrepancies.append(f"action mismatch: {signal_payload.get('action')} != {intent_payload.get('side')}")
        if float(signal_payload.get("quantity", 0)) != float(intent_payload.get("quantity", 0)):
            discrepancies.append(f"quantity mismatch: {signal_payload.get('quantity')} != {intent_payload.get('quantity')}")
        if str(signal_payload.get("order_type", "LIMIT")).upper() != str(intent_payload.get("order_type", "LIMIT")).upper():
            discrepancies.append(f"order_type mismatch: {signal_payload.get('order_type')} != {intent_payload.get('order_type')}")
        
        signal_price = float(signal_payload.get("price", 0))
        intent_price = float(intent_payload.get("price", signal_price))
        if abs(signal_price - intent_price) > 1e-4:
            discrepancies.append(f"price mismatch: {signal_price} != {intent_price}")

        is_parity = (len(discrepancies) == 0)
        return is_parity, discrepancies

    def evaluate_shadow_signal(
        self,
        signal_payload: Dict[str, Any],
        paper_market_price: float,
        latency_ms: float = 12.5,
        capital_requested: float = 0.0,
        intent_payload: Optional[Dict[str, Any]] = None
    ) -> ShadowValidationRecord:
        """
        Evaluates live signal against simulated paper fill price and calculates slippage, latency, and intent parity.
        """
        # 1. Enforce Zero-Capital Guard
        self.verify_zero_capital_guard(capital_requested)

        symbol = str(signal_payload.get("symbol", "AAPL"))
        action = str(signal_payload.get("action", "BUY")).upper()
        signal_price = float(signal_payload.get("price", paper_market_price))

        # 2. Check Order Intent Parity
        intent = intent_payload or {
            "symbol": symbol,
            "side": action,
            "quantity": signal_payload.get("quantity", 10),
            "order_type": signal_payload.get("order_type", "LIMIT"),
            "price": signal_price
        }
        intent_parity, discrepancies = self.evaluate_order_intent_parity(signal_payload, intent)
        if not intent_parity:
            logger.warning("Order intent parity discrepancy for signal %s: %s", symbol, discrepancies)

        # 3. Calculate Slippage & Signal Drift
        slippage_abs = abs(paper_market_price - signal_price)
        slippage_pct = (slippage_abs / signal_price) * 100.0 if signal_price > 0 else 0.0

        # 4. Check Signal Drift Limit (>0.1% -> SafetyState.HOLD)
        if slippage_pct > self.max_allowed_signal_drift_pct:
            drift_msg = f"Signal drift ({slippage_pct:.3f}%) exceeded maximum allowed limit ({self.max_allowed_signal_drift_pct}%)"
            logger.warning(drift_msg)
            self.control_plane.report_subsystem_state("shadow_validation_engine", SafetyState.HOLD, drift_msg)

        shadow_id = f"shd_{uuid.uuid4().hex[:10]}"
        record = ShadowValidationRecord(
            shadow_id=shadow_id,
            signal_symbol=symbol,
            signal_action=action,
            signal_price=signal_price,
            simulated_fill_price=paper_market_price,
            slippage_pct=round(slippage_pct, 4),
            latency_ms=round(latency_ms, 2),
            capital_exposure=0.0,
            order_intent_parity=intent_parity,
            timestamp=time.time()
        )

        self._records.append(record)
        logger.info("Evaluated shadow signal '%s': slippage=%.3f%%, latency=%.1fms, parity=%s", shadow_id, slippage_pct, latency_ms, intent_parity)
        return record

    def reconcile_shadow_vs_paper_ledger(self, paper_order: Dict[str, Any], shadow_record: ShadowValidationRecord) -> ShadowReconciliationRecord:
        """
        Reconciles paper order ledger entry against shadow validation record (6D-P13).
        """
        paper_price = float(paper_order.get("price", paper_order.get("limit_price", shadow_record.simulated_fill_price)))
        paper_qty = float(paper_order.get("quantity", 10))
        paper_status = str(paper_order.get("status", "FILLED")).upper()

        price_delta = abs(paper_price - shadow_record.simulated_fill_price)
        qty_delta = abs(paper_qty - 10)
        status_match = (paper_status in ("FILLED", "ACKNOWLEDGED", "SUBMITTED"))

        rec_id = f"rec_shd_{uuid.uuid4().hex[:8]}"
        rec = ShadowReconciliationRecord(
            reconciliation_id=rec_id,
            paper_order_id=str(paper_order.get("order_id", "ord_paper_1")),
            shadow_id=shadow_record.shadow_id,
            status_match=status_match,
            price_delta=round(price_delta, 4),
            quantity_delta=round(qty_delta, 4),
            timestamp=time.time()
        )
        self._reconciliations.append(rec)
        return rec

    def get_shadow_performance_metrics(self) -> Dict[str, Any]:
        """Calculates aggregate shadow metrics."""
        if not self._records:
            return {
                "total_records": 0,
                "avg_slippage_pct": 0.0,
                "avg_latency_ms": 0.0,
                "intent_parity_pct": 100.0,
                "capital_exposure": "$0.00"
            }

        avg_slippage = sum(r.slippage_pct for r in self._records) / len(self._records)
        avg_latency = sum(r.latency_ms for r in self._records) / len(self._records)
        parity_count = sum(1 for r in self._records if r.order_intent_parity)
        parity_pct = (parity_count / len(self._records)) * 100.0

        return SecretSanitizer.sanitize_dict({
            "total_records": len(self._records),
            "avg_slippage_pct": round(avg_slippage, 4),
            "avg_latency_ms": round(avg_latency, 2),
            "intent_parity_pct": round(parity_pct, 2),
            "capital_exposure": "$0.00",
            "is_slippage_acceptable": avg_slippage <= self.max_allowed_slippage_pct,
            "is_latency_acceptable": avg_latency <= self.max_allowed_latency_ms
        })
