# execution/safety_gate.py
"""
Live Gateway Safety Controls (LiveSafetyGate) for NexTrade (Sub-Phase 4D).
Implements a fail-closed, un-bypassable safety gate evaluating 12 fail-closed barriers (S1–S12)
before order dispatch to concrete BrokerAdapter implementations.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide
from contracts.safety_contracts import (
    SafetyBarrierStatus,
    SafetyBarrierResult,
    SafetyEvaluationContext,
    SafetyEvaluationResult,
    LiveSafetyLimits,
    ExecutionEnvironment,
    OrderIntent,
)
from utils.rate_limiter import SlidingWindowRateLimiter


class LiveSafetyGate:
    """
    Fail-Closed Safety Perimeter Gate wrapping order dispatch to BrokerAdapters.
    """

    def __init__(
        self,
        limits: Optional[LiveSafetyLimits] = None,
        rate_limiter: Optional[SlidingWindowRateLimiter] = None,
        metrics_registry: Optional[Any] = None
    ):
        self.limits = limits or LiveSafetyLimits()
        self.rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            max_requests=self.limits.max_orders_per_minute,
            window_seconds=60.0
        )
        self.metrics_registry = metrics_registry

    def authorize_dispatch(
        self,
        request: BrokerOrderRequest,
        context: SafetyEvaluationContext
    ) -> SafetyEvaluationResult:
        """
        Stage 1 Pre-Authorization Evaluation evaluating all 12 fail-closed safety barriers.
        If ANY barrier evaluates to DENY or UNKNOWN, returns is_authorized = False.
        """
        now = datetime.now(timezone.utc)
        barrier_results: List[SafetyBarrierResult] = []
        denial_reasons: List[str] = []

        try:
            # Stale State Snapshot Guard
            if context.is_stale(now):
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S0_STALE_STATE",
                        barrier_name="Safety Context Freshness Check",
                        status=SafetyBarrierStatus.UNKNOWN,
                        reason="SafetyEvaluationContext timestamp is stale or expired",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("STALE_SAFETY_CONTEXT_SNAPSHOT")

            # S1: LIVE_TRADING_ENABLED Gate
            if context.environment == ExecutionEnvironment.LIVE and not context.live_trading_enabled:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S1_LIVE_TRADING_ENABLED",
                        barrier_name="Live Trading Flag Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason="LIVE environment requested while live_trading_enabled is False",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("LIVE_TRADING_DISABLED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S1_LIVE_TRADING_ENABLED",
                        barrier_name="Live Trading Flag Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Passed environment flag check",
                        evaluated_at=now
                    )
                )

            # S2: Multi-Factor Live Unlock Gate
            if context.environment == ExecutionEnvironment.LIVE:
                if not context.multi_factor_unlock or not context.multi_factor_unlock.is_valid(now):
                    barrier_results.append(
                        SafetyBarrierResult(
                            barrier_id="S2_MFA_UNLOCK",
                            barrier_name="Multi-Factor Unlock Barrier",
                            status=SafetyBarrierStatus.DENY,
                            reason="Missing or expired multi-factor unlock token for LIVE execution",
                            evaluated_at=now
                        )
                    )
                    denial_reasons.append("MFA_UNLOCK_INVALID_OR_EXPIRED")
                else:
                    barrier_results.append(
                        SafetyBarrierResult(
                            barrier_id="S2_MFA_UNLOCK",
                            barrier_name="Multi-Factor Unlock Barrier",
                            status=SafetyBarrierStatus.PASS,
                            reason="Multi-factor unlock token verified",
                            evaluated_at=now
                        )
                    )
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S2_MFA_UNLOCK",
                        barrier_name="Multi-Factor Unlock Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Non-live environment (MFA unlock not required)",
                        evaluated_at=now
                    )
                )

            # S3: Kill Switch & Hard Halt Gate
            if context.kill_switch_mode == "HARD_HALT":
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S3_KILL_SWITCH",
                        barrier_name="Emergency Kill Switch Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason="HARD_HALT active across execution system",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("HARD_HALT_ACTIVE")
            elif context.kill_switch_mode == "REDUCE_ONLY" and context.order_intent == OrderIntent.ENTRY:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S3_KILL_SWITCH",
                        barrier_name="Emergency Kill Switch Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason="REDUCE_ONLY mode active: ENTRY orders strictly prohibited",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("REDUCE_ONLY_ENTRY_PROHIBITED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S3_KILL_SWITCH",
                        barrier_name="Emergency Kill Switch Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Kill switch mode clear",
                        evaluated_at=now
                    )
                )

            # S4: Daily Loss Limit Gate
            if context.daily_loss >= self.limits.max_daily_loss:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S4_DAILY_LOSS_LIMIT",
                        barrier_name="Daily Loss Limit Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Daily loss ({context.daily_loss}) meets or exceeds limit ({self.limits.max_daily_loss})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("MAX_DAILY_LOSS_EXCEEDED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S4_DAILY_LOSS_LIMIT",
                        barrier_name="Daily Loss Limit Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Daily loss within bounds",
                        evaluated_at=now
                    )
                )

            # S5: Maximum Order Notional Gate
            order_notional = request.quantity * (request.limit_price or 100.0)
            if order_notional > self.limits.max_order_notional:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S5_ORDER_NOTIONAL_LIMIT",
                        barrier_name="Maximum Order Notional Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Order notional ({order_notional}) exceeds max limit ({self.limits.max_order_notional})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("MAX_ORDER_NOTIONAL_EXCEEDED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S5_ORDER_NOTIONAL_LIMIT",
                        barrier_name="Maximum Order Notional Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Order notional within bounds",
                        evaluated_at=now
                    )
                )

            # S6: Maximum Position Exposure Gate
            if context.projected_position_exposure > self.limits.max_position_exposure:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S6_POSITION_EXPOSURE_LIMIT",
                        barrier_name="Maximum Position Exposure Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Projected exposure ({context.projected_position_exposure}) exceeds max limit ({self.limits.max_position_exposure})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("MAX_POSITION_EXPOSURE_EXCEEDED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S6_POSITION_EXPOSURE_LIMIT",
                        barrier_name="Maximum Position Exposure Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Position exposure within bounds",
                        evaluated_at=now
                    )
                )

            # S7: Maximum Active Open Orders Gate
            if context.active_open_orders >= self.limits.max_open_orders:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S7_OPEN_ORDER_LIMIT",
                        barrier_name="Active Open Orders Limit Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Active open orders ({context.active_open_orders}) meets max limit ({self.limits.max_open_orders})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("MAX_OPEN_ORDERS_EXCEEDED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S7_OPEN_ORDER_LIMIT",
                        barrier_name="Active Open Orders Limit Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Open orders within bounds",
                        evaluated_at=now
                    )
                )

            # S8: Atomic Rate Limiter Gate
            if not self.rate_limiter.try_acquire():
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S8_RATE_LIMITER",
                        barrier_name="Atomic Rate Limiter Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason="Order dispatch rate limit exhausted",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("RATE_LIMIT_EXHAUSTED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S8_RATE_LIMITER",
                        barrier_name="Atomic Rate Limiter Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Rate limiter token acquired",
                        evaluated_at=now
                    )
                )

            # S9: Credential Status Gate
            if context.broker_credentials_status != "VALID":
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S9_CREDENTIALS",
                        barrier_name="Broker Credential Verification Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Broker credentials invalid or degraded ({context.broker_credentials_status})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("INVALID_BROKER_CREDENTIALS")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S9_CREDENTIALS",
                        barrier_name="Broker Credential Verification Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Credentials valid",
                        evaluated_at=now
                    )
                )

            # S10: Broker Connection Health Gate
            if context.broker_connection_status not in ("CONNECTED", "HEALTHY"):
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S10_BROKER_HEALTH",
                        barrier_name="Broker Connection Health Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Broker connection unhealthy ({context.broker_connection_status})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("BROKER_CONNECTION_UNHEALTHY")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S10_BROKER_HEALTH",
                        barrier_name="Broker Connection Health Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Broker connection healthy",
                        evaluated_at=now
                    )
                )

            # S11: Audit Logger Health Gate
            if context.audit_logger_status != "OK":
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S11_AUDIT_LOGGER",
                        barrier_name="Audit Logger Health Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason=f"Audit logger degraded or corrupt ({context.audit_logger_status})",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("AUDIT_LOGGER_DEGRADED")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S11_AUDIT_LOGGER",
                        barrier_name="Audit Logger Health Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Audit logger healthy",
                        evaluated_at=now
                    )
                )

            # S12: Environment Execution Permissions Gate
            if context.environment == ExecutionEnvironment.SHADOW:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S12_ENVIRONMENT_PERMISSIONS",
                        barrier_name="Environment Permission Barrier",
                        status=SafetyBarrierStatus.DENY,
                        reason="SHADOW environment prohibits external broker order dispatches",
                        evaluated_at=now
                    )
                )
                denial_reasons.append("SHADOW_ENVIRONMENT_NO_DISPATCH")
            else:
                barrier_results.append(
                    SafetyBarrierResult(
                        barrier_id="S12_ENVIRONMENT_PERMISSIONS",
                        barrier_name="Environment Permission Barrier",
                        status=SafetyBarrierStatus.PASS,
                        reason="Environment dispatch permitted",
                        evaluated_at=now
                    )
                )

        except Exception as ex:
            # Exception Safety: Fail-closed on evaluation error
            barrier_results.append(
                SafetyBarrierResult(
                    barrier_id="S_EXCEPTION_FAIL_CLOSED",
                    barrier_name="Evaluation Exception Guard",
                    status=SafetyBarrierStatus.UNKNOWN,
                    reason=f"Safety gate evaluation raised exception: {str(ex)}",
                    evaluated_at=now
                )
            )
            denial_reasons.append("SAFETY_GATE_EVALUATION_EXCEPTION")

        # Fail-Closed Rule: EVERY barrier must be PASS
        is_authorized = len(denial_reasons) == 0 and all(r.status == SafetyBarrierStatus.PASS for r in barrier_results)

        return SafetyEvaluationResult(
            is_authorized=is_authorized,
            barrier_results=barrier_results,
            denial_reasons=denial_reasons,
            timestamp=now
        )

    def verify_just_in_time_dispatch(
        self,
        request: BrokerOrderRequest,
        context: SafetyEvaluationContext
    ) -> SafetyEvaluationResult:
        """
        Stage 2 Just-In-Time Safety Recheck immediately before BrokerAdapter submission.
        Revalidates volatile fields (live flag, kill switch, connection health, audit logger).
        """
        return self.authorize_dispatch(request, context)
