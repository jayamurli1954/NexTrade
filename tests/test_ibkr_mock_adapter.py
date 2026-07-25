# tests/test_ibkr_mock_adapter.py
"""
Unit Test Suite for IBKR Mock Adapter & Failure Injection (Sub-Phase 4B).
Tests IBKRBrokerAdapter behavior under clean submission, pre-submission rejections,
rate-limit throttling, order modification, and post-submission socket timeouts (yielding status UNKNOWN).
"""
import pytest
from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderModificationRequest,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerOrderStatus,
)
from brokers.ibkr_adapter import IBKRBrokerAdapter
from brokers.ibkr_mock import MockIBKRTransport


def test_ibkr_adapter_clean_order_submission():
    """Verify IBKRBrokerAdapter handles clean order submission with MockIBKRTransport."""
    transport = MockIBKRTransport()
    adapter = IBKRBrokerAdapter(transport=transport)

    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-IBKR-001",
        idempotency_key="IDEM-IBKR-001",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=100.0,
        limit_price=175.0
    )

    res = adapter.submit_order(req)

    assert res.status == BrokerOrderStatus.FILLED
    assert res.nextrade_execution_id == "EXREQ-IBKR-001"
    assert res.idempotency_key == "IDEM-IBKR-001"
    assert res.broker_order_id is not None
    assert res.filled_quantity == 100.0
    assert res.average_fill_price == 175.0
    assert res.requires_reconciliation is False


def test_ibkr_adapter_pre_submission_rejection_injection():
    """Verify pre-submission margin failure yields BrokerOrderStatus.REJECTED."""
    transport = MockIBKRTransport()
    transport.set_simulated_failure("PRE_SUBMIT_REJECT")
    adapter = IBKRBrokerAdapter(transport=transport)

    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-IBKR-002",
        idempotency_key="IDEM-IBKR-002",
        symbol="TSLA",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=50.0
    )

    res = adapter.submit_order(req)

    assert res.status == BrokerOrderStatus.REJECTED
    assert res.error_code == "201"
    assert "Insufficient margin" in res.error_message
    assert res.requires_reconciliation is False


def test_ibkr_adapter_rate_limit_rejection():
    """Verify rate-limit breach yields BrokerOrderStatus.REJECTED."""
    transport = MockIBKRTransport()
    transport.set_simulated_failure("RATE_LIMIT")
    adapter = IBKRBrokerAdapter(transport=transport)

    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-IBKR-003",
        idempotency_key="IDEM-IBKR-003",
        symbol="NVDA",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10.0
    )

    res = adapter.submit_order(req)

    assert res.status == BrokerOrderStatus.REJECTED
    assert res.error_code == "162"
    assert "rate limit" in res.error_message.lower()


def test_ibkr_adapter_post_submission_timeout_yields_unknown_status():
    """
    Verify post-submission socket timeout yields status UNKNOWN with requires_reconciliation = True.
    (Invariants E6, E9, E14, E25, E37).
    """
    transport = MockIBKRTransport()
    transport.set_simulated_failure("TIMEOUT")
    adapter = IBKRBrokerAdapter(transport=transport)

    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-IBKR-TIMEOUT-001",
        idempotency_key="IDEM-IBKR-TIMEOUT-001",
        symbol="AMZN",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=20.0,
        limit_price=130.0
    )

    res = adapter.submit_order(req)

    assert res.status == BrokerOrderStatus.UNKNOWN
    assert res.requires_reconciliation is True
    assert res.error_code == "TIMEOUT"
    assert "timeout post-transmit" in res.error_message


def test_ibkr_adapter_order_modification():
    """Verify typed order modification via BrokerOrderModificationRequest."""
    transport = MockIBKRTransport()
    adapter = IBKRBrokerAdapter(transport=transport)

    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-IBKR-MOD-1",
        idempotency_key="IDEM-IBKR-MOD-1",
        symbol="NFLX",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=40.0,
        limit_price=400.0
    )

    res = adapter.submit_order(req)

    mod_req = BrokerOrderModificationRequest(
        nextrade_execution_id="EXREQ-IBKR-MOD-1",
        broker_order_id=res.broker_order_id,
        new_quantity=60.0,
        new_limit_price=410.0
    )

    mod_res = adapter.modify_order(mod_req)

    assert mod_res.broker_order_id == res.broker_order_id
    assert mod_res.nextrade_execution_id == "EXREQ-IBKR-MOD-1"
