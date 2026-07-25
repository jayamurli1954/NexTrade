# tests/test_observability.py
"""
Adversarial Telemetry Metrics & Alert Test Suite for NexTrade (Sub-Phase 4F).
Verifies 7-pillar telemetry metrics collection, structured alert record metadata,
threshold alert evaluation, subsystem health aggregation, report staleness detection, and non-blocking exports.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta

from contracts.observability_contracts import (
    AlertLevel,
    MetricCategory,
    MetricType,
    SubsystemHealthStatus,
    SystemHealthReport,
)
from observability.metrics_registry import MetricsRegistry
from observability.alert_engine import AlertEngine
from observability.observability_manager import ObservabilityManager
from observability.exporter import HealthExporter


def test_metrics_registry_7_pillar_collection():
    """Verify MetricsRegistry records counters, gauges, and histograms across categories."""
    reg = MetricsRegistry()

    # 1. Counter
    reg.increment_counter("nextrade_safety_evaluations_total", MetricCategory.SAFETY, labels={"status": "AUTHORIZED"})
    reg.increment_counter("nextrade_safety_evaluations_total", MetricCategory.SAFETY, labels={"status": "AUTHORIZED"})

    # 2. Gauge
    reg.set_gauge("nextrade_reconciliation_pending_orders", MetricCategory.RECONCILIATION, 3.0)

    # 3. Histogram
    reg.observe_histogram("nextrade_execution_latency_seconds", MetricCategory.GATEWAY, 0.045)
    reg.observe_histogram("nextrade_execution_latency_seconds", MetricCategory.GATEWAY, 0.055)

    snapshot = reg.get_snapshot()

    assert snapshot.get("nextrade_safety_evaluations_total{status=AUTHORIZED}") == 2.0
    assert snapshot.get("nextrade_reconciliation_pending_orders") == 3.0
    assert snapshot.get("nextrade_execution_latency_seconds_count") == 2.0
    assert snapshot.get("nextrade_execution_latency_seconds_avg") == 0.05


def test_alert_engine_explicit_metadata_and_thresholds():
    """Verify AlertEngine creates AlertRecords with explicit severity, threshold, and action metadata."""
    engine = AlertEngine()

    snapshot = {
        "broker_connection_status": "DISCONNECTED",
        "daily_loss": 4500.0,
        "max_daily_loss": 5000.0,
        "dlq_count": 15,
        "unreconciled_orders": 2,
    }

    alerts = engine.evaluate_thresholds(snapshot)

    assert len(alerts) >= 4
    severities = [a.severity for a in alerts]

    assert AlertLevel.CRITICAL in severities
    assert AlertLevel.WARNING in severities

    # Check alert metadata fields
    disc_alert = [a for a in alerts if a.source_subsystem == "BROKER_SESSION"][0]
    assert disc_alert.alert_id.startswith("ALT-")
    assert disc_alert.condition == "Broker socket connection is DISCONNECTED"
    assert disc_alert.threshold == "status == CONNECTED"
    assert len(disc_alert.recommended_action) > 0


def test_observability_manager_health_aggregation_and_staleness():
    """Verify ObservabilityManager aggregates health status and evaluates report staleness."""
    manager = ObservabilityManager()

    # Healthy Snapshot
    snapshot_healthy = {"broker_connection_status": "CONNECTED", "daily_loss": 100.0, "max_daily_loss": 5000.0}
    report1 = manager.generate_health_report(snapshot_healthy)

    assert report1.overall_status == SubsystemHealthStatus.HEALTHY
    assert report1.is_stale() is False

    # Stale report test
    old_time = datetime.now(timezone.utc) - timedelta(seconds=20)
    stale_report = SystemHealthReport(
        report_id="RPT-STALE",
        overall_status=SubsystemHealthStatus.HEALTHY,
        subsystem_statuses={},
        active_alerts=[],
        metrics_snapshot={},
        timestamp=old_time,
        max_report_age_seconds=10.0
    )
    assert stale_report.is_stale() is True


def test_health_exporter_json_and_prometheus_output():
    """Verify HealthExporter formats reports cleanly as JSON and Prometheus text."""
    manager = ObservabilityManager()
    manager.metrics.increment_counter("nextrade_events_total", MetricCategory.EVENT_BUS, 10.0)

    report = manager.generate_health_report()
    json_out = HealthExporter.export_json(report)

    assert "report_id" in json_out
    assert "overall_status" in json_out

    parsed = json.loads(json_out)
    assert parsed["overall_status"] == "HEALTHY"

    prom_out = HealthExporter.export_prometheus(manager.metrics)
    assert "nextrade_events_total" in prom_out
