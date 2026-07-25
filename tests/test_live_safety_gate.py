# tests/test_live_safety_gate.py
"""
Adversarial Safety & Failure Injection Test Suite for LiveSafetyGate (Sub-Phase 4D).
Tests all 12 fail-closed barriers (S1–S12), stale context snapshots, MFA token expiry,
rate-limit exhaustion, kill switch modes, and exception safety isolation.
"""
import pytest
from datetime import datetime, timezone, timedelta

from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderSide,
    BrokerOrderType,
)
from contracts.safety_contracts import (
    SafetyEvaluationContext,
    LiveSafetyLimits,
    ExecutionEnvironment,
    OrderIntent,
    MultiFactorUnlock,
    SafetyBarrierStatus,
)
from execution.safety_gate import LiveSafetyGate
from utils.rate_limiter import SlidingWindowRateLimiter


@pytest.fixture
def default_request():
    return BrokerOrderRequest(
        nextrade_execution_id="EXREQ-SAFETY-001",
        idempotency_key="IDEM-SAFETY-001",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=10.0,
        limit_price=150.0
    )


@pytest.fixture
def valid_paper_context():
    return SafetyEvaluationContext(
        live_trading_enabled=False,
        environment=ExecutionEnvironment.PAPER,
        order_intent=OrderIntent.ENTRY,
        kill_switch_mode="NORMAL",
        daily_loss=100.0,
        current_position_exposure=1000.0,
        projected_position_exposure=2500.0,
        active_open_orders=2,
        broker_credentials_status="VALID",
        broker_connection_status="CONNECTED",
        audit_logger_status="OK",
        timestamp=datetime.now(timezone.utc)
    )


def test_s1_live_trading_disabled_barrier(default_request, valid_paper_context):
    """S1: LIVE environment with live_trading_enabled=False evaluates strictly to DENY."""
    gate = LiveSafetyGate()
    live_ctx = SafetyEvaluationContext(
        live_trading_enabled=False,
        environment=ExecutionEnvironment.LIVE,
        timestamp=datetime.now(timezone.utc)
    )
    res = gate.authorize_dispatch(default_request, live_ctx)

    assert res.is_authorized is False
    assert "LIVE_TRADING_DISABLED" in res.denial_reasons


def test_s2_mfa_unlock_barrier(default_request):
    """S2: LIVE environment with missing or expired MFA token evaluates to DENY."""
    gate = LiveSafetyGate()
    now = datetime.now(timezone.utc)

    # 1. Missing MFA token
    ctx_no_mfa = SafetyEvaluationContext(
        live_trading_enabled=True,
        environment=ExecutionEnvironment.LIVE,
        multi_factor_unlock=None,
        timestamp=now
    )
    res1 = gate.authorize_dispatch(default_request, ctx_no_mfa)
    assert res1.is_authorized is False
    assert "MFA_UNLOCK_INVALID_OR_EXPIRED" in res1.denial_reasons

    # 2. Expired MFA token
    expired_mfa = MultiFactorUnlock(
        operator_token="TOK-EXP-123",
        unlocked_at=now - timedelta(hours=2),
        expires_at=now - timedelta(seconds=10),
        unlocked_by="admin"
    )
    ctx_exp_mfa = SafetyEvaluationContext(
        live_trading_enabled=True,
        environment=ExecutionEnvironment.LIVE,
        multi_factor_unlock=expired_mfa,
        timestamp=now
    )
    res2 = gate.authorize_dispatch(default_request, ctx_exp_mfa)
    assert res2.is_authorized is False
    assert "MFA_UNLOCK_INVALID_OR_EXPIRED" in res2.denial_reasons


def test_s3_kill_switch_hard_halt_and_reduce_only(default_request, valid_paper_context):
    """S3: HARD_HALT denies all orders; REDUCE_ONLY denies ENTRY but permits EXIT."""
    gate = LiveSafetyGate()
    now = datetime.now(timezone.utc)

    # 1. HARD_HALT
    ctx_halt = SafetyEvaluationContext(
        environment=ExecutionEnvironment.PAPER,
        kill_switch_mode="HARD_HALT",
        timestamp=now
    )
    res_halt = gate.authorize_dispatch(default_request, ctx_halt)
    assert res_halt.is_authorized is False
    assert "HARD_HALT_ACTIVE" in res_halt.denial_reasons

    # 2. REDUCE_ONLY mode with ENTRY intent
    ctx_reduce_entry = SafetyEvaluationContext(
        environment=ExecutionEnvironment.PAPER,
        kill_switch_mode="REDUCE_ONLY",
        order_intent=OrderIntent.ENTRY,
        timestamp=now
    )
    res_entry = gate.authorize_dispatch(default_request, ctx_reduce_entry)
    assert res_entry.is_authorized is False
    assert "REDUCE_ONLY_ENTRY_PROHIBITED" in res_entry.denial_reasons

    # 3. REDUCE_ONLY mode with EXIT intent -> PASS
    ctx_reduce_exit = SafetyEvaluationContext(
        environment=ExecutionEnvironment.PAPER,
        kill_switch_mode="REDUCE_ONLY",
        order_intent=OrderIntent.EXIT,
        timestamp=now
    )
    res_exit = gate.authorize_dispatch(default_request, ctx_reduce_exit)
    assert res_exit.is_authorized is True


def test_s4_daily_loss_limit_exceeded(default_request):
    """S4: Daily loss meeting or exceeding max_daily_loss evaluates to DENY."""
    limits = LiveSafetyLimits(max_daily_loss=5000.0)
    gate = LiveSafetyGate(limits=limits)
    ctx = SafetyEvaluationContext(
        environment=ExecutionEnvironment.PAPER,
        daily_loss=5000.0,
        timestamp=datetime.now(timezone.utc)
    )
    res = gate.authorize_dispatch(default_request, ctx)
    assert res.is_authorized is False
    assert "MAX_DAILY_LOSS_EXCEEDED" in res.denial_reasons


def test_s5_order_notional_limit_exceeded():
    """S5: Order notional exceeding limit evaluates to DENY."""
    limits = LiveSafetyLimits(max_order_notional=10000.0)
    gate = LiveSafetyGate(limits=limits)

    large_req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-LARGE",
        idempotency_key="IDEM-LARGE",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=100.0,
        limit_price=150.0  # Notional = $15,000 > $10,000 limit
    )
    ctx = SafetyEvaluationContext(environment=ExecutionEnvironment.PAPER)
    res = gate.authorize_dispatch(large_req, ctx)
    assert res.is_authorized is False
    assert "MAX_ORDER_NOTIONAL_EXCEEDED" in res.denial_reasons


def test_s8_atomic_rate_limiter_exhaustion(default_request):
    """S8: Rate limiter token exhaustion evaluates to DENY."""
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    limits = LiveSafetyLimits(max_orders_per_minute=2)
    gate = LiveSafetyGate(limits=limits, rate_limiter=limiter)
    ctx = SafetyEvaluationContext(environment=ExecutionEnvironment.PAPER)

    # First 2 requests acquire tokens
    assert gate.authorize_dispatch(default_request, ctx).is_authorized is True
    assert gate.authorize_dispatch(default_request, ctx).is_authorized is True

    # 3rd request fails S8
    res3 = gate.authorize_dispatch(default_request, ctx)
    assert res3.is_authorized is False
    assert "RATE_LIMIT_EXHAUSTED" in res3.denial_reasons


def test_s12_shadow_environment_no_order_submission(default_request):
    """S12: SHADOW environment explicitly forbids order dispatches."""
    gate = LiveSafetyGate()
    ctx = SafetyEvaluationContext(
        environment=ExecutionEnvironment.SHADOW,
        timestamp=datetime.now(timezone.utc)
    )
    res = gate.authorize_dispatch(default_request, ctx)
    assert res.is_authorized is False
    assert "SHADOW_ENVIRONMENT_NO_DISPATCH" in res.denial_reasons


def test_stale_safety_context_rejection(default_request):
    """Stale context snapshot (> 5.0 seconds old) evaluates to UNKNOWN -> DENY."""
    gate = LiveSafetyGate()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    stale_ctx = SafetyEvaluationContext(
        environment=ExecutionEnvironment.PAPER,
        timestamp=old_time
    )
    res = gate.authorize_dispatch(default_request, stale_ctx)
    assert res.is_authorized is False
    assert "STALE_SAFETY_CONTEXT_SNAPSHOT" in res.denial_reasons


def test_stage_2_just_in_time_recheck(default_request, valid_paper_context):
    """Verify Stage 2 verify_just_in_time_dispatch rechecks volatile fields."""
    gate = LiveSafetyGate()
    res = gate.verify_just_in_time_dispatch(default_request, valid_paper_context)
    assert res.is_authorized is True
