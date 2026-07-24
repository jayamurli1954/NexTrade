# risk/risk_engine.py
"""
Canonical Risk Engine Orchestrator for NexTrade.
Composes Phase 2B (PositionSizer), Phase 2C (PortfolioRiskEvaluator),
and Phase 2D (KillSwitchManager) into a single unbypassable pre-trade control point.
Enforces the strict quantity chain invariant: 0 <= Q_final <= Q_2D <= Q_2C <= Q_2B <= Q_requested.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from types import MappingProxyType

from contracts.signal import Signal
from contracts.order import OrderSide
from contracts.position import Position
from contracts.risk import (
    RiskContext,
    RiskLimits,
    OrderIntent,
    RiskDecision,
    RiskDecisionStatus,
    RiskCheckResult,
    RiskRuleCategory,
    RiskRuleSeverity,
)
from risk.position_sizer import PositionSizer, InstrumentInfo, SizingStatus
from risk.risk_limits import PortfolioRiskEvaluator, PortfolioCheckResult
from risk.kill_switch import KillSwitchManager, KillSwitchCheckResult


class RiskEngine:
    """
    Central Pre-Trade Control Point composing 2B, 2C, and 2D into an unbypassable decision.
    """

    def __init__(
        self,
        sizer: Optional[PositionSizer] = None,
        portfolio_evaluator: Optional[PortfolioRiskEvaluator] = None,
        kill_switch_manager: Optional[KillSwitchManager] = None
    ):
        self.sizer = sizer or PositionSizer()
        self.portfolio_evaluator = portfolio_evaluator or PortfolioRiskEvaluator()
        self.kill_switch_manager = kill_switch_manager or KillSwitchManager()

    def evaluate_order_request(
        self,
        signal: Signal,
        order_side: OrderSide,
        order_intent: OrderIntent,
        requested_quantity: int,
        context: RiskContext,
        limits: RiskLimits,
        instrument: Optional[InstrumentInfo] = None,
        broker_name: str = "DEFAULT",
        sector_mapping: Optional[Dict[str, str]] = None
    ) -> RiskDecision:
        """
        Evaluate order request through 2B -> 2C -> 2D pipeline and return canonical RiskDecision.
        """
        now = datetime.now(timezone.utc)
        decision_id = f"RD-{uuid.uuid4().hex[:8]}"
        checks: List[RiskCheckResult] = []

        if requested_quantity <= 0:
            return self._fail_closed_decision(
                decision_id=decision_id,
                signal_id=signal.signal_id,
                order_intent=order_intent,
                requested_quantity=requested_quantity,
                decision_status=RiskDecisionStatus.REJECTED,
                modification_reason="Invalid requested_quantity; must be positive",
                limiting_phase="PHASE_2E",
                timestamp=now
            )

        try:
            # ------------------------------------------------------------------
            # Stage 1: Phase 2B Position Sizing Math (Q_2B)
            # ------------------------------------------------------------------
            sizing_res = self.sizer.calculate_quantity(
                signal=signal,
                order_side=order_side,
                order_intent=order_intent,
                requested_quantity=requested_quantity,
                context=context,
                limits=limits,
                instrument=instrument
            )
            q_2b = sizing_res.approved_quantity

            # Short-circuit on Phase 2B hard rejection (Q_2B == 0)
            if q_2b == 0 or sizing_res.status in (SizingStatus.INVALID_INPUT, SizingStatus.REJECTED):
                reason_str = sizing_res.reason or f"Position sizing rejected: {sizing_res.reason_code.value}"
                checks.append(RiskCheckResult(
                    rule_name="PositionSizingRule",
                    category=RiskRuleCategory.POSITION_SIZING,
                    passed=False,
                    severity=RiskRuleSeverity.BLOCKING,
                    reason=reason_str,
                    metrics={"sizing_status": sizing_res.status.value, "reason_code": sizing_res.reason_code.value}
                ))
                return RiskDecision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    order_intent=order_intent,
                    decision=RiskDecisionStatus.REJECTED,
                    requested_quantity=requested_quantity,
                    approved_quantity=0,
                    modification_reason=reason_str,
                    checks_evaluated=tuple(checks),
                    timestamp=now
                )

            checks.append(RiskCheckResult(
                rule_name="PositionSizingRule",
                category=RiskRuleCategory.POSITION_SIZING,
                passed=True,
                severity=RiskRuleSeverity.INFO,
                reason=f"Position sizing authorized {q_2b} units",
                metrics={"q_2b": q_2b, "risk_amount": str(sizing_res.risk_amount)}
            ))

            # ------------------------------------------------------------------
            # Stage 2: Phase 2C Portfolio Exposure Limits (Q_2C)
            # ------------------------------------------------------------------
            entry_price = Decimal(str(signal.entry_price))
            lot_size = instrument.lot_size if instrument else 1

            portfolio_res = self.portfolio_evaluator.evaluate_portfolio_risk(
                symbol=signal.symbol,
                exchange=signal.exchange,
                entry_price=entry_price,
                order_side=order_side,
                order_intent=order_intent,
                candidate_quantity=q_2b,
                context=context,
                limits=limits,
                lot_size=lot_size,
                sector_mapping=sector_mapping
            )
            q_2c = portfolio_res.approved_quantity
            checks.extend(portfolio_res.checks_evaluated)

            # Short-circuit on Phase 2C hard rejection (Q_2C == 0)
            if q_2c == 0 or not portfolio_res.passed:
                reason_str = portfolio_res.reason or "Portfolio exposure limits breached"
                return RiskDecision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    order_intent=order_intent,
                    decision=RiskDecisionStatus.REJECTED,
                    requested_quantity=requested_quantity,
                    approved_quantity=0,
                    modification_reason=reason_str,
                    checks_evaluated=tuple(checks),
                    timestamp=now
                )

            # ------------------------------------------------------------------
            # Stage 3: Phase 2D Safety Gates & Kill Switches (Q_2D)
            # ------------------------------------------------------------------
            kill_res = self.kill_switch_manager.evaluate_kill_switch(
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                broker_name=broker_name,
                order_intent=order_intent,
                candidate_quantity=q_2c
            )
            q_2d = kill_res.authorized_quantity

            if kill_res.is_blocked:
                # Check if rejection is due to broker availability feed or risk policy block
                is_broker_off = (
                    kill_res.blocking_level == kill_res.blocking_level.BROKER and
                    "unavailable" in (kill_res.reason or "").lower()
                ) if kill_res.blocking_level else False

                decision_status = RiskDecisionStatus.REJECTED if is_broker_off else RiskDecisionStatus.BLOCKED_BY_KILL_SWITCH
                reason_str = kill_res.reason or "Blocked by active kill switch / safety gate"

                checks.append(RiskCheckResult(
                    rule_name="KillSwitchRule",
                    category=RiskRuleCategory.KILL_SWITCH,
                    passed=False,
                    severity=RiskRuleSeverity.BLOCKING,
                    reason=reason_str,
                    metrics={
                        "blocking_level": kill_res.blocking_level.value if kill_res.blocking_level else None,
                        "breaker_type": kill_res.breaker_type.value if kill_res.breaker_type else None
                    }
                ))

                return RiskDecision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    order_intent=order_intent,
                    decision=decision_status,
                    requested_quantity=requested_quantity,
                    approved_quantity=0,
                    modification_reason=reason_str,
                    checks_evaluated=tuple(checks),
                    timestamp=now
                )

            checks.append(RiskCheckResult(
                rule_name="KillSwitchRule",
                category=RiskRuleCategory.KILL_SWITCH,
                passed=True,
                severity=RiskRuleSeverity.INFO,
                reason="Safety gates passed",
                metrics={"authorized_q2d": q_2d}
            ))

            # ------------------------------------------------------------------
            # Stage 4: Master Invariant Validation & Decision Resolution
            # Enforces: 0 <= Q_final <= Q_2D <= Q_2C <= Q_2B <= Q_requested
            # ------------------------------------------------------------------
            q_final = q_2d

            if not (0 <= q_final <= q_2d <= q_2c <= q_2b <= requested_quantity):
                return self._fail_closed_decision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    order_intent=order_intent,
                    requested_quantity=requested_quantity,
                    decision_status=RiskDecisionStatus.REJECTED,
                    modification_reason=f"RISK_QUANTITY_INVARIANT_VIOLATION: Q_final({q_final}) > Q_2D({q_2d}) > Q_2C({q_2c}) > Q_2B({q_2b}) > Q_req({requested_quantity})",
                    limiting_phase="PHASE_2E",
                    timestamp=now
                )

            # Resolve Decision Status: APPROVED or MODIFIED
            decision_status = RiskDecisionStatus.APPROVED if q_final == requested_quantity else RiskDecisionStatus.MODIFIED

            limiting_phase = None
            if q_final < requested_quantity:
                if q_final == q_2d and q_2d < q_2c:
                    limiting_phase = "PHASE_2D"
                elif q_2c < q_2b:
                    limiting_phase = "PHASE_2C"
                else:
                    limiting_phase = "PHASE_2B"

            reason_str = "Order fully approved" if decision_status == RiskDecisionStatus.APPROVED else f"Quantity modified from {requested_quantity} to {q_final} by {limiting_phase}"

            return RiskDecision(
                decision_id=decision_id,
                signal_id=signal.signal_id,
                order_intent=order_intent,
                decision=decision_status,
                requested_quantity=requested_quantity,
                approved_quantity=q_final,
                modification_reason=reason_str,
                checks_evaluated=tuple(checks),
                timestamp=now
            )

        except Exception as e:
            # FAIL-CLOSED for execution; retain internal diagnostic trace
            return self._fail_closed_decision(
                decision_id=decision_id,
                signal_id=signal.signal_id,
                order_intent=order_intent,
                requested_quantity=requested_quantity,
                decision_status=RiskDecisionStatus.REJECTED,
                modification_reason="RISK_ENGINE_INTERNAL_ERROR",
                limiting_phase="PHASE_2E",
                timestamp=now,
                internal_diagnostics={"exception_type": type(e).__name__, "exception_message": str(e)}
            )

    def _fail_closed_decision(
        self,
        decision_id: str,
        signal_id: Optional[str],
        order_intent: OrderIntent,
        requested_quantity: int,
        decision_status: RiskDecisionStatus,
        modification_reason: str,
        limiting_phase: str,
        timestamp: datetime,
        internal_diagnostics: Optional[Dict[str, Any]] = None
    ) -> RiskDecision:
        """Helper to safely generate fail-closed RiskDecision."""
        metrics_dict = {"fail_closed": True, "limiting_phase": limiting_phase}
        if internal_diagnostics:
            metrics_dict.update(internal_diagnostics)

        check_fail = RiskCheckResult(
            rule_name="FailClosedRule",
            category=RiskRuleCategory.ACCOUNT,
            passed=False,
            severity=RiskRuleSeverity.BLOCKING,
            reason=modification_reason,
            metrics=MappingProxyType(metrics_dict)
        )

        return RiskDecision(
            decision_id=decision_id,
            signal_id=signal_id,
            order_intent=order_intent,
            decision=decision_status,
            requested_quantity=requested_quantity,
            approved_quantity=0,
            modification_reason=modification_reason,
            checks_evaluated=(check_fail,),
            timestamp=timestamp
        )
