# observability/observability_manager.py
"""
Unified Observability Manager for NexTrade (Sub-Phase 4F).
Read-only, failure-isolated orchestrator producing SystemHealthReports,
staleness health signals, and system health status snapshots.
"""
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from contracts.observability_contracts import (
    SubsystemHealthStatus,
    SystemHealthReport,
    AlertLevel,
)
from observability.metrics_registry import MetricsRegistry
from observability.alert_engine import AlertEngine


class ObservabilityManager:
    """
    Read-only orchestrator aggregating telemetry metrics, alert evaluation, and health reporting.
    """

    def __init__(
        self,
        metrics_registry: Optional[MetricsRegistry] = None,
        alert_engine: Optional[AlertEngine] = None
    ):
        self.metrics = metrics_registry or MetricsRegistry()
        self.alert_engine = alert_engine or AlertEngine()
        self._lock = threading.RLock()

    def generate_health_report(self, context_state: Optional[Dict[str, Any]] = None) -> SystemHealthReport:
        """
        Aggregates system state and metrics snapshot into a SystemHealthReport.
        Failure-isolated: Always returns a valid report structure even on internal errors.
        """
        now = datetime.now(timezone.utc)
        report_id = f"RPT-{uuid.uuid4().hex[:12].upper()}"

        try:
            snapshot = self.metrics.get_snapshot()
            if context_state:
                snapshot.update(context_state)

            # Evaluate alert thresholds
            active_alerts = self.alert_engine.evaluate_thresholds(snapshot)

            # Determine Subsystem Statuses
            subsystem_statuses = {
                "SAFETY_GATE": SubsystemHealthStatus.HEALTHY,
                "EXECUTION": SubsystemHealthStatus.HEALTHY,
                "BROKER_CONNECTION": SubsystemHealthStatus.HEALTHY,
                "EVENT_BUS": SubsystemHealthStatus.HEALTHY,
                "RECONCILIATION": SubsystemHealthStatus.HEALTHY,
            }

            # Map alerts to subsystem health statuses
            for alert in active_alerts:
                if alert.source_subsystem in subsystem_statuses:
                    if alert.severity in (AlertLevel.CRITICAL, AlertLevel.FATAL):
                        subsystem_statuses[alert.source_subsystem] = SubsystemHealthStatus.UNHEALTHY
                    elif alert.severity == AlertLevel.WARNING:
                        if subsystem_statuses[alert.source_subsystem] != SubsystemHealthStatus.UNHEALTHY:
                            subsystem_statuses[alert.source_subsystem] = SubsystemHealthStatus.DEGRADED

            # Determine Overall Status
            if any(s == SubsystemHealthStatus.UNHEALTHY for s in subsystem_statuses.values()):
                overall_status = SubsystemHealthStatus.UNHEALTHY
            elif any(s == SubsystemHealthStatus.DEGRADED for s in subsystem_statuses.values()):
                overall_status = SubsystemHealthStatus.DEGRADED
            else:
                overall_status = SubsystemHealthStatus.HEALTHY

            # Convert snapshot to numeric float dictionary for report
            numeric_snapshot = {k: float(v) for k, v in snapshot.items() if isinstance(v, (int, float))}

            return SystemHealthReport(
                report_id=report_id,
                overall_status=overall_status,
                subsystem_statuses=subsystem_statuses,
                active_alerts=active_alerts,
                metrics_snapshot=numeric_snapshot,
                timestamp=now,
                max_report_age_seconds=10.0
            )

        except Exception:
            # Failure-isolated fallback
            return SystemHealthReport(
                report_id=report_id,
                overall_status=SubsystemHealthStatus.UNKNOWN,
                subsystem_statuses={"SAFETY_GATE": SubsystemHealthStatus.UNKNOWN},
                active_alerts=[],
                metrics_snapshot={},
                timestamp=now,
                max_report_age_seconds=10.0
            )
