# tests/test_shadow_engine.py
"""
Adversarial Shadow Mode Test Suite for NexTrade (Sub-Phase 4G).
Verifies deterministic tick matching, limit order fill/miss logic, slippage calculations,
SQLite & JSONL dual persistence durability, ShadowEvaluator reports, and ShadowRunner pipeline execution.
"""
import os
import pytest
from datetime import datetime, timezone

from contracts.execution import ExecutionRequest, OrderSide
from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide, BrokerOrderType
from contracts.shadow_contracts import ShadowOrderStatus
from execution.shadow_engine import ShadowEngine
from storage.shadow_store import ShadowStore
from execution.shadow_evaluator import ShadowEvaluator
from execution.shadow_runner import ShadowRunner
from observability.metrics_registry import MetricsRegistry


@pytest.fixture
def tmp_shadow_store(tmp_path):
    db_file = str(tmp_path / "test_shadow.db")
    jsonl_file = str(tmp_path / "test_shadow.jsonl")
    return ShadowStore(db_path=db_file, jsonl_path=jsonl_file)


def test_shadow_engine_deterministic_buy_fill_and_slippage():
    """Verify BUY order fills when tick price <= limit price and applies fixed slippage."""
    engine = ShadowEngine(fixed_slippage_bps=5.0)

    buy_req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-SHD-01",
        idempotency_key="IDEM-SHD-01",
        symbol="AAPL",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=10.0,
        limit_price=150.0
    )

    # 1. Market price 149.0 <= 150.0 limit -> FILLED with 5 bps slippage
    rec_filled = engine.match_shadow_order(buy_req, market_tick_price=149.0)
    assert rec_filled.status == ShadowOrderStatus.SHADOW_FILLED
    assert rec_filled.simulated_fill_price == round(149.0 * (1 + 5/10000), 4)
    assert rec_filled.slippage_bps == 5.0

    # 2. Market price 151.0 > 150.0 limit -> MISSED
    rec_missed = engine.match_shadow_order(buy_req, market_tick_price=151.0)
    assert rec_missed.status == ShadowOrderStatus.SHADOW_MISSED
    assert rec_missed.simulated_fill_price == 0.0


def test_shadow_store_dual_persistence(tmp_shadow_store):
    """Verify ShadowStore saves records to SQLite DB and JSONL log file."""
    engine = ShadowEngine()
    req = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-STORE-01",
        idempotency_key="IDEM-STORE-01",
        symbol="MSFT",
        side=BrokerOrderSide.SELL,
        order_type=BrokerOrderType.LIMIT,
        quantity=5.0,
        limit_price=300.0
    )

    rec = engine.match_shadow_order(req, market_tick_price=305.0)
    assert tmp_shadow_store.save_record(rec) is True

    # Verify SQLite reading
    db_records = tmp_shadow_store.get_records()
    assert len(db_records) == 1
    assert db_records[0].shadow_id == rec.shadow_id
    assert db_records[0].symbol == "MSFT"

    # Verify JSONL log file presence
    assert os.path.exists(tmp_shadow_store.jsonl_path)
    with open(tmp_shadow_store.jsonl_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        assert "MSFT" in lines[0]


def test_shadow_evaluator_comparison_report(tmp_shadow_store):
    """Verify ShadowEvaluator computes aggregate statistical metrics."""
    engine = ShadowEngine(fixed_slippage_bps=2.0)
    evaluator = ShadowEvaluator(shadow_store=tmp_shadow_store)

    req1 = BrokerOrderRequest(
        nextrade_execution_id="EXREQ-REP-01",
        idempotency_key="IDEM-REP-01",
        symbol="NVDA",
        side=BrokerOrderSide.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=1.0,
        limit_price=500.0
    )

    # 1 Fill, 1 Miss
    rec1 = engine.match_shadow_order(req1, market_tick_price=490.0)
    rec2 = engine.match_shadow_order(req1, market_tick_price=510.0)

    tmp_shadow_store.save_record(rec1)
    tmp_shadow_store.save_record(rec2)

    report = evaluator.generate_comparison_report()

    assert report.total_shadow_orders == 2
    assert report.simulated_fill_count == 1
    assert report.missed_fill_count == 1
    assert report.simulated_fill_rate == 50.0
    assert report.average_slippage_bps == 2.0


def test_shadow_runner_pipeline(tmp_shadow_store):
    """Verify ShadowRunner pipeline processes ExecutionRequest into ShadowExecutionRecord without submitting orders."""
    metrics = MetricsRegistry()
    runner = ShadowRunner(shadow_store=tmp_shadow_store, metrics_registry=metrics)

    exec_req = ExecutionRequest(
        execution_request_id="EXREQ-RUN-01",
        idempotency_key="IDEM-RUN-01",
        risk_decision_id="RD-RUN-01",
        symbol="GOOGL",
        exchange="NASDAQ",
        order_side=OrderSide.BUY,
        requested_quantity=10,
        approved_quantity=10,
        execution_quantity=10
    )

    rec = runner.process_shadow_execution(exec_req, market_tick_price=140.0)

    assert rec.symbol == "GOOGL"
    assert rec.status == ShadowOrderStatus.SHADOW_FILLED
    assert "SHADOW_ENVIRONMENT_NO_DISPATCH" in rec.safety_gate_denial_reasons

    # Check metrics
    snapshot = metrics.get_snapshot()
    assert snapshot.get("nextrade_shadow_orders_total{status=SHADOW_FILLED,symbol=GOOGL}") == 1.0
