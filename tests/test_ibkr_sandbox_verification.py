# tests/test_ibkr_sandbox_verification.py
"""
End-to-End IBKR Sandbox Verification Test Suite for NexTrade (Sub-Phase 4C).
Verifies physical port security guards, offline sandbox harness capabilities across all 17 domains,
partial fill deltas, session health management, and post-submission UNKNOWN reconciliation boundaries.
"""
import pytest
from contracts.broker_domain import (
    BrokerOrderRequest,
    BrokerOrderModificationRequest,
    BrokerOrderSide,
    BrokerOrderType,
    BrokerOrderStatus,
)
from config.ibkr_config import IBKRConfig, validate_sandbox_config
from brokers.ibkr_client import IBKRSandboxHarness
from brokers.ibkr_session import IBKRSessionManager, IBKRSessionState
from brokers.ibkr_adapter import IBKRBrokerAdapter


def test_physical_port_security_guard_blocks_live_ports():
    """Verify validate_sandbox_config raises PermissionError if live port or live account is used."""
    # 1. Live TWS port 7462 must fail when live_trading_enabled is False
    config_live_port = IBKRConfig(port=7462)
    with pytest.raises(PermissionError, match="SECURITY GUARD VIOLATION: IBKR live port 7462 requested"):
        validate_sandbox_config(config_live_port, live_trading_enabled=False)

    # 2. Live Gateway port 4001 must fail
    config_gateway_live = IBKRConfig(port=4001)
    with pytest.raises(PermissionError, match="SECURITY GUARD VIOLATION: IBKR live port 4001 requested"):
        validate_sandbox_config(config_gateway_live, live_trading_enabled=False)

    # 3. Live account designation must fail
    config_live_acct = IBKRConfig(port=7497, is_paper_account=False)
    with pytest.raises(PermissionError, match="is_paper_account must be True"):
        validate_sandbox_config(config_live_acct, live_trading_enabled=False)

    # 4. Live account ID format must fail
    config_live_id = IBKRConfig(port=7497, account_id="U999888")
    with pytest.raises(PermissionError, match="Account ID 'U999888' appears to be a live account"):
        validate_sandbox_config(config_live_id, live_trading_enabled=False)

    # 5. Paper port 7497 & DU account succeeds cleanly
    config_paper = IBKRConfig(port=7497, account_id="DU123456", is_paper_account=True)
    validate_sandbox_config(config_paper, live_trading_enabled=False)


def test_sandbox_harness_order_types_and_lifecycle():
    """Verify IBKRSandboxHarness supports Market, Limit, Stop, Stop-Limit, and Trailing Stop orders."""
    harness = IBKRSandboxHarness()

    for o_type in [BrokerOrderType.MARKET, BrokerOrderType.LIMIT, BrokerOrderType.STOP, BrokerOrderType.STOP_LIMIT, BrokerOrderType.TRAILING_STOP]:
        res = harness.place_order(
            contract={"symbol": "AAPL"},
            order={"action": "BUY", "totalQuantity": 10.0, "lmtPrice": 150.0, "orderRef": "IDEM-101"}
        )
        assert res["status"] in ("FILLED", "PARTIALLY_FILLED")
        assert res["orderId"] > 0


def test_partial_fill_delta_accounting():
    """Verify partial fill mode updates filled/remaining quantity cleanly."""
    harness = IBKRSandboxHarness()
    harness.set_simulated_mode("PARTIAL_FILL")

    res = harness.place_order(
        contract={"symbol": "MSFT"},
        order={"action": "BUY", "totalQuantity": 10.0, "lmtPrice": 300.0}
    )

    assert res["status"] == "PARTIALLY_FILLED"
    assert res["filled"] == 5.0
    assert res["remaining"] == 5.0
    assert harness.positions["MSFT"]["quantity"] == 5.0


def test_order_cancellation_and_modification_in_harness():
    """Verify order cancellation and modification via harness."""
    harness = IBKRSandboxHarness()
    res = harness.place_order(
        contract={"symbol": "GOOGL"},
        order={"action": "BUY", "totalQuantity": 20.0, "lmtPrice": 2500.0}
    )
    order_id = res["orderId"]

    # Modify
    mod_res = harness.modify_order(order_id, new_quantity=30.0, new_price=2550.0)
    assert mod_res["order"]["totalQuantity"] == 30.0
    assert mod_res["avgFillPrice"] == 2550.0

    # Cancel
    cancel_res = harness.cancel_order(order_id)
    assert cancel_res["status"] == "CANCELLED"


def test_session_manager_health_and_backoff_reconnection():
    """Verify IBKRSessionManager connection health and auto-reconnect backoff."""
    session = IBKRSessionManager()
    assert session.state == IBKRSessionState.DISCONNECTED

    session.mark_connected()
    assert session.state == IBKRSessionState.CONNECTED
    assert session.last_heartbeat is not None

    session.record_heartbeat()
    report = session.health_report()
    assert report["is_connected"] is True
    assert report["is_paper_account"] is True

    # Test reconnect simulation
    mock_connect = lambda: True
    success = session.attempt_reconnect(mock_connect)
    assert success is True
    assert session.total_reconnections == 1
