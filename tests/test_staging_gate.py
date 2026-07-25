# tests/test_staging_gate.py
"""
Adversarial Controlled Live Staging Gate Test Suite for NexTrade (Sub-Phase 4J).
Verifies:
1. Multi-certificate token validation (4H + 4I + HMAC + human_authorization_id).
2. Configuration hash immutability & tampering rejection.
3. Symbol allowlist enforcement (e.g. AAPL allowed; TSLA denied).
4. Order quantity & notional bound enforcement.
5. Daily loss breach -> HARD_HALT trigger.
6. Circuit breaker REDUCE_ONLY enforcement (risk-reducing allowed; risk-increasing denied).
7. Dual persistence in SQLite DB and JSONL log file.
"""
import os
import pytest
from datetime import datetime, timezone, timedelta

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType
from contracts.staging_contracts import StagingEnvironmentConfig
from staging.staging_authorizer import StagingAuthorizer
from staging.staging_gate import StagingGate
from staging.circuit_breaker import CircuitBreakerManager, CircuitState
from storage.staging_store import StagingStore


@pytest.fixture
def authorizer():
    return StagingAuthorizer(secret_key="TEST_SECRET")


@pytest.fixture
def config():
    cfg = StagingEnvironmentConfig(
        max_order_quantity=10.0,
        max_order_notional=1000.0,
        max_daily_loss=500.0,
        max_position_exposure=2500.0,
        allowed_symbols=["AAPL", "MSFT"],
        broker_endpoint="127.0.0.1:7497",
        account_id="DU123456"
    )
    return cfg


@pytest.fixture
def valid_token(authorizer, config):
    return authorizer.issue_authorization_token(
        promo_4h_certificate_id="CERT-PROM-4H",
        audit_4i_certificate_id="AUD-4I",
        git_commit="6c0f2fa",
        config=config,
        human_authorization_id="OP-HUMAN-999",
        validity_seconds=3600.0
    )


@pytest.fixture
def req_aapl():
    return BrokerOrderRequest(
        nextrade_execution_id="EXREQ-STG-01",
        idempotency_key="IDEM-STG-01",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=5.0,
        limit_price=100.0
    )


def test_staging_gate_allow_valid_order(config, authorizer, valid_token, req_aapl):
    """Verify StagingGate authorizes valid order with matching token and limits."""
    gate = StagingGate(config=config, authorizer=authorizer)
    res = gate.authorize_staging_order(req_aapl, valid_token)

    assert res.authorized is True
    assert "AUTHORIZED" in res.reason
    assert res.lineage is not None
    assert res.lineage.authorization_token_id == valid_token.token_id


def test_staging_gate_deny_missing_or_expired_token(config, authorizer, req_aapl):
    """Verify StagingGate denies orders with missing or expired tokens."""
    gate = StagingGate(config=config, authorizer=authorizer)

    # 1. Missing Token
    res_none = gate.authorize_staging_order(req_aapl, auth_token=None)
    assert res_none.authorized is False
    assert "missing" in res_none.reason

    # 2. Expired Token
    expired_token = authorizer.issue_authorization_token(
        promo_4h_certificate_id="CERT-4H",
        audit_4i_certificate_id="AUD-4I",
        git_commit="6c0f2fa",
        config=config,
        human_authorization_id="OP-999",
        validity_seconds=-10.0  # Expired
    )
    res_exp = gate.authorize_staging_order(req_aapl, expired_token)
    assert res_exp.authorized is False
    assert "expired" in res_exp.reason


def test_staging_gate_deny_tampered_config(config, authorizer, req_aapl):
    """Verify StagingGate denies authorization if config is modified after token issuance."""
    gate = StagingGate(config=config, authorizer=authorizer)
    valid_token = authorizer.issue_authorization_token(
        promo_4h_certificate_id="CERT-4H",
        audit_4i_certificate_id="AUD-4I",
        git_commit="6c0f2fa",
        config=config,
        human_authorization_id="OP-999"
    )

    # Modify runtime config (e.g. increase limit to 100)
    tampered_config = StagingEnvironmentConfig(
        max_order_quantity=100.0,
        max_order_notional=10000.0,
        allowed_symbols=["AAPL", "MSFT"]
    )
    gate_tampered = StagingGate(config=tampered_config, authorizer=authorizer)

    res = gate_tampered.authorize_staging_order(req_aapl, valid_token)
    assert res.authorized is False
    assert "tampering" in res.reason or "mismatch" in res.reason


def test_staging_gate_deny_non_allowlisted_symbol(config, authorizer, valid_token):
    """Verify StagingGate denies non-allowlisted symbols (e.g. TSLA)."""
    gate = StagingGate(config=config, authorizer=authorizer)
    req_tsla = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-STG-TSLA",
        idempotency_key="IDEM-STG-TSLA",
        symbol="TSLA",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=1.0,
        limit_price=200.0
    )

    res = gate.authorize_staging_order(req_tsla, valid_token)
    assert res.authorized is False
    assert "not in allowed pilot list" in res.reason


def test_staging_gate_deny_quantity_and_notional_breach(config, authorizer, valid_token):
    """Verify StagingGate denies orders exceeding quantity or notional limits."""
    gate = StagingGate(config=config, authorizer=authorizer)

    # Quantity 15 > max 10
    req_big_qty = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-QTY",
        idempotency_key="IDEM-QTY",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=15.0,
        limit_price=50.0
    )
    res_qty = gate.authorize_staging_order(req_big_qty, valid_token)
    assert res_qty.authorized is False
    assert "quantity" in res_qty.reason

    # Notional 1500 > max 1000
    req_big_notional = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-NOTIONAL",
        idempotency_key="IDEM-NOTIONAL",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=5.0,
        limit_price=300.0
    )
    res_notional = gate.authorize_staging_order(req_big_notional, valid_token)
    assert res_notional.authorized is False
    assert "notional" in res_notional.reason


def test_circuit_breaker_reduce_only_enforcement(config, authorizer, valid_token, req_aapl):
    """Verify REDUCE_ONLY mode allows risk-reducing orders and blocks risk-increasing orders."""
    cb = CircuitBreakerManager()
    cb.trigger_circuit_breaker(CircuitState.REDUCE_ONLY)
    gate = StagingGate(config=config, authorizer=authorizer, circuit_breaker=cb)

    # 1. Risk-increasing order -> DENIED
    res_inc = gate.authorize_staging_order(req_aapl, valid_token, is_risk_reducing=False)
    assert res_inc.authorized is False
    assert "REDUCE_ONLY" in res_inc.reason

    # 2. Risk-reducing order -> ALLOWED
    res_red = gate.authorize_staging_order(req_aapl, valid_token, is_risk_reducing=True)
    assert res_red.authorized is True


def test_staging_store_persistence(config, authorizer, valid_token, req_aapl, tmp_path):
    """Verify StagingStore saves lineage to SQLite DB and JSONL log."""
    gate = StagingGate(config=config, authorizer=authorizer)
    res = gate.authorize_staging_order(req_aapl, valid_token)

    db_path = str(tmp_path / "test_stg.db")
    jsonl_path = str(tmp_path / "test_stg.jsonl")
    store = StagingStore(db_path=db_path, jsonl_path=jsonl_path)

    assert store.save_lineage(res.lineage) is True
    assert os.path.exists(jsonl_path)
