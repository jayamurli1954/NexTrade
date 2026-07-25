# observability/exporter.py
"""
Structured Health & Telemetry Exporter for NexTrade (Sub-Phase 4F).
Exports SystemHealthReports and MetricsRegistry snapshots as structured JSON dictionaries
or Prometheus-formatted text streams. Non-blocking and failure-isolated.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any

from contracts.observability_contracts import SystemHealthReport
from observability.metrics_registry import MetricsRegistry


class HealthExporter:
    """
    Non-blocking exporter converting system health and metrics into JSON or Prometheus formats.
    """

    @staticmethod
    def export_json(report: SystemHealthReport) -> str:
        """
        Exports a SystemHealthReport as a JSON formatted string.
        """
        try:
            data = {
                "report_id": report.report_id,
                "overall_status": report.overall_status.value,
                "subsystem_statuses": {k: v.value for k, v in report.subsystem_statuses.items()},
                "active_alerts_count": len(report.active_alerts),
                "active_alerts": [
                    {
                        "alert_id": a.alert_id,
                        "severity": a.severity.value,
                        "source_subsystem": a.source_subsystem,
                        "condition": a.condition,
                        "threshold": a.threshold,
                        "recommended_action": a.recommended_action,
                        "timestamp": a.timestamp.isoformat()
                    }
                    for a in report.active_alerts
                ],
                "metrics_snapshot": report.metrics_snapshot,
                "timestamp": report.timestamp.isoformat(),
                "is_stale": report.is_stale()
            }
            return json.dumps(data, indent=2)
        except Exception as ex:
            return json.dumps({"error": f"JSON export failure: {str(ex)}", "status": "UNKNOWN"})

    @staticmethod
    def export_prometheus(registry: MetricsRegistry) -> str:
        """
        Exports MetricsRegistry snapshot as Prometheus text format.
        """
        try:
            snapshot = registry.get_snapshot()
            lines = ["# HELP nextrade_metrics NexTrade Phase 4 Telemetry Metrics", "# TYPE nextrade_metrics gauge"]
            for key, val in sorted(snapshot.items()):
                # Format metric name for prometheus
                clean_key = key.replace("-", "_").replace(".", "_")
                lines.append(f"{clean_key} {val}")
            return "\n".join(lines)
        except Exception as ex:
            return f"# Exporter error: {str(ex)}"
