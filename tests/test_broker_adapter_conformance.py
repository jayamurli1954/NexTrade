# tests/test_broker_adapter_conformance.py
"""
Conformance & Interface Test Suite for Broker Adapters (Sub-Phase 4B).
Verifies canonical broker domain contracts, one-way translation boundaries,
capability validation, error taxonomy classification, and PaperBrokerAdapter conformance.
"""
import pytest
from datetime import datetime, timezone

from contracts.execution import ExecutionRequest, ExecutionResult, ExecutionStatus, OrderSide
from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderModificationRequest,
    BrokerOrderResult,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerOrderStatus,
    BrokerTimeInForce,
)
from contracts.broker_translation import (
    to_broker_order_request,
    to_execution_result,
    map_broker_status_to_execution_status,
)
from contracts.broker_error import (
    BrokerError,
    BrokerErrorType,
    is_pre_submission_error,
    is_post_submission_ambiguous,
    classify_error_to_status,
)
from contracts.broker_capabilities import BrokerCapabilities, CapabilityValidator
from brokers.paper_adapter import PaperBrokerAdapter


def test_one_way_translation_request_and_lineage_preservation():
    """Verify ExecutionRequest translates to BrokerOrderRequest while preserving lineage."""
    exec_req = ExecutionRequest(
        execution_request_id="EXREQ-TEST-001",
        idempotency_key="IDEM-TEST-001",
        risk_decision_id="RISK-TEST-001",
        symbol="AAPL",
        exchange="NASDAQ",
        order_side=OrderSide.BUY,
        requested_quantity=100,
        approved_quantity=100,
        execution_quantity=100,
        order_type="LIMIT",
        limit_price=150.0
    )

    broker_req = to_broker_order_request(exec_req)

    assert isinstance(broker_req, BrokerOrderRequest)
    assert broker_req.nextrade_execution_id == "EXREQ-TEST-001"
    assert broker_req.idempotency_key == "IDEM-TEST-001"
    assert broker_req.symbol == "AAPL"
    assert broker_req.side == BrokerOrderSide.BUY
    assert broker_req.order_type == BrokerOrderType.LIMIT
    assert broker_req.quantity == 100.0
    assert broker_req.limit_price == 150.0
    assert broker_req.metadata["risk_decision_id"] == "RISK-TEST-001"


def test_reverse_translation_broker_result_to_execution_result():
    """Verify BrokerOrderResult translates back to ExecutionResult."""
    exec_req = ExecutionRequest(
        execution_request_id="EXREQ-TEST-002",
        idempotency_key="IDEM-TEST-002",
        risk_decision_id="RISK-TEST-002",
        symbol="MSFT",
        exchange="NASDAQ",
        order_side=OrderSide.BUY,
        requested_quantity=50,
        approved_quantity=50,
        execution_quantity=50
    )

    broker_res = BrokerOrderResult(
        nextrade_execution_id="EXREQ-TEST-002",
        idempotency_key="IDEM-TEST-002",
        broker_order_id="BROKER-ORD-999",
        status=BrokerOrderStatus.FILLED,
        filled_quantity=50.0,
        remaining_quantity=0.0,
        average_fill_price=310.0
    )

    exec_res = to_execution_result(exec_req, broker_res)

    assert isinstance(exec_res, ExecutionResult)
    assert exec_res.execution_request_id == "EXREQ-TEST-002"
    assert exec_res.risk_decision_id == "RISK-TEST-002"
    assert exec_res.broker_order_id == "BROKER-ORD-999"
    assert exec_res.status == ExecutionStatus.FILLED
    assert exec_res.filled_quantity == 50
    assert exec_res.remaining_quantity == 0
    assert exec_res.average_fill_price == 310.0


def test_capability_validator_enforces_supported_types():
    """Verify CapabilityValidator rejects unsupported order types."""
    capabilities = BrokerCapabilities(
        broker_name="RestrictedBroker",
        supports_market_orders=True,
        supports_limit_orders=False,
        supports_trailing_stops=False
    )

    valid_req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-CAP-1",
        idempotency_key="IDEM-CAP-1",
        symbol="GOOGL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10.0
    )
    # Should not raise exception
    CapabilityValidator.validate(capabilities, valid_req)

    invalid_req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-CAP-2",
        idempotency_key="IDEM-CAP-2",
        symbol="GOOGL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=10.0,
        limit_price=2800.0
    )
    with pytest.raises(ValueError, match="does not support order type 'LIMIT'"):
        CapabilityValidator.validate(capabilities, invalid_req)


def test_error_taxonomy_classification():
    """Verify pre-submission error vs post-submission ambiguity classification."""
    err_pre = BrokerError(
        error_type=BrokerErrorType.INSUFFICIENT_FUNDS,
        message="Account balance low",
        is_pre_submission=True
    )
    assert is_pre_submission_error(err_pre.error_type) is True
    assert is_post_submission_ambiguous(err_pre.error_type) is False
    assert classify_error_to_status(err_pre) == BrokerOrderStatus.REJECTED

    err_post = BrokerError(
        error_type=BrokerErrorType.TIMEOUT,
        message="Socket timeout after transmit",
        is_pre_submission=False
    )
    assert is_pre_submission_error(err_post.error_type) is False
    assert is_post_submission_ambiguous(err_post.error_type) is True
    assert classify_error_to_status(err_post) == BrokerOrderStatus.UNKNOWN


def test_paper_broker_adapter_conformance():
    """Verify PaperBrokerAdapter implements BrokerAdapter interface methods cleanly."""
    adapter = PaperBrokerAdapter()

    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-PAPER-01",
        idempotency_key="IDEM-PAPER-01",
        symbol="TSLA",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=25.0,
        limit_price=200.0
    )

    res = adapter.submit_order(req)
    assert res.status == BrokerOrderStatus.FILLED
    assert res.broker_order_id is not None
    assert res.filled_quantity == 25.0

    # Query order state
    ord_state = adapter.get_order(res.broker_order_id)
    assert ord_state is not None
    assert ord_state.broker_order_id == res.broker_order_id
    assert ord_state.symbol == "TSLA"

    # Query account
    acct = adapter.get_account()
    assert acct.is_live is False
    assert acct.total_equity > 0

    # Health check
    health = adapter.health_check()
    assert health["status"] == "HEALTHY"
    assert health["is_live"] is False
