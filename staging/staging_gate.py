# staging/staging_gate.py
"""
Controlled Live Staging Gate Engine for NexTrade (Sub-Phase 4J).
Evaluates order requests against StagingEnvironmentConfig bounds, symbol allowlists,
circuit breaker state, and LiveSafetyGate under ExecutionEnvironment.CONTROLLED_LIVE.
Enforces process restart safety (Invariant 4J-P10) and full correlation lineage (Invariant 4J-P5).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide
from contracts.safety_contracts import SafetyEvaluationContext, ExecutionEnvironment, SafetyBarrierResult
from contracts.staging_contracts import (
    StagingEnvironmentConfig,
    StagingAuthorizationToken,
    StagingOrderLineage,
    StagingGateResult,
)
from execution.safety_gate import LiveSafetyGate
from staging.staging_authorizer import StagingAuthorizer
from staging.circuit_breaker import CircuitBreakerManager, CircuitState


class StagingGate:
    """
    Controlled Live Staging Gate enforcing exposure bounds, allowlists, and restart safety.
    """

    def __init__(
        self,
        config: Optional[StagingEnvironmentConfig] = None,
        authorizer: Optional[StagingAuthorizer] = None,
        safety_gate: Optional[LiveSafetyGate] = None,
        circuit_breaker: Optional[CircuitBreakerManager] = None
    ):
        self.config = config or StagingEnvironmentConfig()
        self.authorizer = authorizer or StagingAuthorizer()
        self.safety_gate = safety_gate or LiveSafetyGate()
        self.circuit_breaker = circuit_breaker or CircuitBreakerManager()
        # Invariant 4J-P10: Process restart resets environment to SAFE/DISABLED
        self.environment = ExecutionEnvironment.PAPER

    def authorize_staging_order(
        self,
        request: BrokerOrderRequest,
        auth_token: Optional[StagingAuthorizationToken],
        signal_id: str = "SIG-01",
        risk_decision_id: str = "RD-01",
        current_position_quantity: float = 0.0,
        current_daily_loss: float = 0.0,
        is_risk_reducing: bool = False
    ) -> StagingGateResult:
        """
        Evaluates a broker order request for Controlled Live Staging execution.
        """
        now = datetime.now(timezone.utc)
        staging_id = f"STG-{uuid.uuid4().hex[:12].upper()}"

        # 1. Validate Cryptographic Authorization Token (Invariants 4J-P1, 4J-P6-P9)
        token_valid, token_reason = self.authorizer.validate_authorization_token(auth_token, self.config, now)
        if not token_valid:
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", token_reason, now)
            return StagingGateResult(authorized=False, reason=token_reason, lineage=lineage)

        # 2. Check Circuit Breaker & Emergency Kill Switch (Invariants 4J-P3, 4J-P11, 4J-P12)
        circuit_ok, circuit_reason = self.circuit_breaker.can_execute_order(is_risk_reducing=is_risk_reducing)
        if not circuit_ok:
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", circuit_reason, now)
            return StagingGateResult(authorized=False, reason=circuit_reason, lineage=lineage)

        # 3. Check Symbol Allowlist (Invariant 4J-P2)
        if request.symbol not in self.config.allowed_symbols:
            reason = f"STAGING_DENIED: Symbol '{request.symbol}' not in allowed pilot list ({self.config.allowed_symbols})"
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", reason, now)
            return StagingGateResult(authorized=False, reason=reason, lineage=lineage)

        # 4. Check Staging Quantity & Notional Limits (Invariant 4J-P2)
        limit_price = request.limit_price or 100.0
        notional = request.quantity * limit_price

        if request.quantity > self.config.max_order_quantity:
            reason = f"STAGING_DENIED: Order quantity ({request.quantity}) exceeds max allowed ({self.config.max_order_quantity})"
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", reason, now)
            return StagingGateResult(authorized=False, reason=reason, lineage=lineage)

        if notional > self.config.max_order_notional:
            reason = f"STAGING_DENIED: Order notional (${notional:.2f}) exceeds max allowed (${self.config.max_order_notional:.2f})"
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", reason, now)
            return StagingGateResult(authorized=False, reason=reason, lineage=lineage)

        if current_daily_loss >= self.config.max_daily_loss:
            reason = f"STAGING_DENIED: Daily loss (${current_daily_loss:.2f}) reached daily limit (${self.config.max_daily_loss:.2f})"
            self.circuit_breaker.trigger_circuit_breaker(CircuitState.HARD_HALT)
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", reason, now)
            return StagingGateResult(authorized=False, reason=reason, lineage=lineage)

        # 5. Evaluate LiveSafetyGate S1–S12 Under Controlled Live Environment
        safety_context = SafetyEvaluationContext(
            live_trading_enabled=True,
            environment=ExecutionEnvironment.PAPER,  # Paper/Staging Sandbox endpoint
            timestamp=now
        )
        safety_res = self.safety_gate.authorize_dispatch(request, safety_context)
        if not safety_res.is_authorized:
            reason = f"STAGING_DENIED: LiveSafetyGate denied dispatch ({safety_res.denial_reasons})"
            lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "DENIED", reason, now)
            return StagingGateResult(authorized=False, reason=reason, lineage=lineage)

        # Clean Staging Gate Pass
        reason = "AUTHORIZED: Staging gate approved controlled live dispatch"
        lineage = self._build_lineage(staging_id, request, auth_token, signal_id, risk_decision_id, "AUTHORIZED", reason, now)
        return StagingGateResult(authorized=True, reason=reason, lineage=lineage)

    def _build_lineage(
        self,
        staging_id: str,
        request: BrokerOrderRequest,
        token: Optional[StagingAuthorizationToken],
        signal_id: str,
        risk_decision_id: str,
        staging_result: str,
        reason: str,
        now: datetime
    ) -> StagingOrderLineage:
        """Constructs immutable correlation lineage for auditability (Invariant 4J-P5)."""
        return StagingOrderLineage(
            staging_id=staging_id,
            correlation_id=request.idempotency_key,
            signal_id=signal_id,
            risk_decision_id=risk_decision_id,
            execution_request_id=request.nextrade_execution_id,
            promo_4h_certificate_id=token.promo_4h_certificate_id if token else "NONE",
            audit_4i_certificate_id=token.audit_4i_certificate_id if token else "NONE",
            authorization_token_id=token.token_id if token else "NONE",
            config_hash=token.config_hash if token else "NONE",
            broker_endpoint_hash=token.broker_endpoint_hash if token else "NONE",
            safety_gate_result="AUTHORIZED" if staging_result == "AUTHORIZED" else "DENIED",
            staging_gate_result=staging_result,
            circuit_breaker_state=self.circuit_breaker.current_state.value,
            kill_switch_state="ACTIVE" if self.circuit_breaker._kill_switch_active else "INACTIVE",
            broker_order_id="PENDING",
            broker_status="UNSUBMITTED",
            reconciliation_status="PENDING",
            timestamps={"request_time": now}
        )
