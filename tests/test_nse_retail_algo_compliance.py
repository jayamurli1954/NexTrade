# tests/test_nse_retail_algo_compliance.py
"""
NSE retail algo framework guards (NSE/INVG/69255, NSE/INSP/77559):
- unknown order types never fall back to MARKET,
- algo MARKET orders are blocked on Indian exchanges (S14),
- orders are capped at 10 per second (S13).
"""
import pytest

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType
from contracts.broker_translation import to_broker_order_request
from contracts.execution import ExecutionRequest
from contracts.safety_contracts import (
    ExecutionEnvironment,
    LiveSafetyLimits,
    SafetyEvaluationContext,
)
from brokers.ibkr_translator import IBKRTranslator
from execution.safety_gate import LiveSafetyGate
from utils.rate_limiter import SlidingWindowRateLimiter


def _order(order_type=BrokerOrderType.LIMIT, exchange=None, limit_price=100.0):
    return BrokerOrderRequest(
        nextrade_execution_id="EXREQ-NSE-001",
        idempotency_key="IDEM-NSE-001",
        symbol="RELIANCE",
        side=BrokerOrderSide.BUY,
        order_type=order_type,
        quantity=1.0,
        limit_price=limit_price,
        metadata={"exchange": exchange} if exchange else {},
    )


def _ctx():
    return SafetyEvaluationContext(environment=ExecutionEnvironment.PAPER)


# --- S14: market-order ban on Indian venues ---------------------------------

@pytest.mark.parametrize("exchange", ["NSE", "nfo", "BSE", "MCX"])
def test_market_order_denied_on_indian_exchange(exchange):
    res = LiveSafetyGate().authorize_dispatch(_order(BrokerOrderType.MARKET, exchange, None), _ctx())
    assert res.is_authorized is False
    assert "MARKET_ORDER_NOT_ALLOWED_ON_INDIAN_EXCHANGE" in res.denial_reasons


def test_limit_order_allowed_on_nse():
    res = LiveSafetyGate().authorize_dispatch(_order(BrokerOrderType.LIMIT, "NSE"), _ctx())
    assert res.is_authorized is True


def test_market_order_allowed_on_non_indian_venue():
    res = LiveSafetyGate().authorize_dispatch(_order(BrokerOrderType.MARKET, "SMART", None), _ctx())
    assert res.is_authorized is True


# --- S13: 10 orders-per-second cap -------------------------------------------

def test_default_limit_is_ten_orders_per_second():
    assert LiveSafetyLimits().max_orders_per_second == 10


def test_eleventh_order_in_one_second_denied():
    gate = LiveSafetyGate(
        limits=LiveSafetyLimits(max_orders_per_minute=1000),
        per_second_rate_limiter=_FrozenClockLimiter(max_requests=10),
    )
    for _ in range(10):
        assert gate.authorize_dispatch(_order(exchange="NSE"), _ctx()).is_authorized is True
    res = gate.authorize_dispatch(_order(exchange="NSE"), _ctx())
    assert res.is_authorized is False
    assert "ORDERS_PER_SECOND_EXCEEDED" in res.denial_reasons


class _FrozenClockLimiter(SlidingWindowRateLimiter):
    """Per-second limiter with a fixed clock so the test cannot straddle a second boundary."""

    def __init__(self, max_requests):
        super().__init__(max_requests=max_requests, window_seconds=1.0)

    def try_acquire(self, now_timestamp=None):
        return super().try_acquire(now_timestamp=1_000_000.0)


# --- Translators fail closed on unknown order types --------------------------

def test_ibkr_translator_rejects_unknown_order_type():
    req = _order()
    object.__setattr__(req, "order_type", "BOGUS") if _is_frozen(req) else setattr(req, "order_type", "BOGUS")
    with pytest.raises(ValueError):
        IBKRTranslator.to_ibkr_contract_and_order(req)


def test_execution_translation_rejects_unknown_order_type():
    exec_req = _execution_request("BRACKET")
    with pytest.raises(ValueError):
        to_broker_order_request(exec_req)


@pytest.mark.parametrize("raw, expected", [
    ("LIMIT", BrokerOrderType.LIMIT),
    ("lmt", BrokerOrderType.LIMIT),
    ("MARKET", BrokerOrderType.MARKET),
    ("STOP_LIMIT", BrokerOrderType.STOP_LIMIT),
])
def test_execution_translation_known_types(raw, expected):
    assert to_broker_order_request(_execution_request(raw)).order_type == expected


def _is_frozen(obj):
    params = getattr(type(obj), "__dataclass_params__", None)
    return bool(params and params.frozen)


def _execution_request(order_type):
    import dataclasses
    fields = {f.name: f for f in dataclasses.fields(ExecutionRequest)}
    values = {
        "execution_request_id": "EXREQ-T-1",
        "idempotency_key": "IDEM-T-1",
        "risk_decision_id": "RISK-T-1",
        "signal_id": "SIG-T-1",
        "strategy_id": "STRAT-T-1",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "order_side": "BUY",
        "order_type": order_type,
        "requested_quantity": 1,
        "approved_quantity": 1,
        "execution_quantity": 1,
        "limit_price": 100.0,
    }
    kwargs = {k: v for k, v in values.items() if k in fields}
    missing = [
        n for n, f in fields.items()
        if n not in kwargs
        and f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING
    ]
    if missing:
        pytest.skip(f"ExecutionRequest needs extra fields for this test: {missing}")
    return ExecutionRequest(**kwargs)
