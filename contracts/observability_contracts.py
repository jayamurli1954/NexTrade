# contracts/observability_contracts.py
"""
Canonical Observability Contracts & Domain Models for NexTrade (Sub-Phase 4F).
Defines strongly typed, frozen dataclasses for 7-pillar telemetry metrics,
explicit alert records, subsystem health status, and system health reports.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class MetricCategory(str, Enum):
    SAFETY = "SAFETY"
    GATEWAY = "GATEWAY"
    BROKER_SESSION = "BROKER_SESSION"
    EVENT_BUS = "EVENT_BUS"
    RECONCILIATION = "RECONCILIATION"
    DLQ = "DLQ"
    SYSTEM_HEALTH = "SYSTEM_HEALTH"


class MetricType(str, Enum):
    COUNTER = "COUNTER"
    GAUGE = "GAUGE"
    HISTOGRAM = "HISTOGRAM"


class SubsystemHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MetricRecord:
    """
    Immutable telemetry metric observation.
    """
    name: str
    category: MetricCategory
    metric_type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AlertRecord:
    """
    Structured incident alert containing explicit metadata and recommended action.
    """
    alert_id: str
    severity: AlertLevel
    source_subsystem: str
    condition: str
    threshold: str
    recommended_action: str
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SystemHealthReport:
    """
    Aggregated point-in-time system health report with freshness staleness detection.
    """
    report_id: str
    overall_status: SubsystemHealthStatus
    subsystem_statuses: Dict[str, SubsystemHealthStatus]
    active_alerts: List[AlertRecord]
    metrics_snapshot: Dict[str, float]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    max_report_age_seconds: float = 10.0

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        """Returns True if report timestamp is older than max_report_age_seconds."""
        current_time = now or datetime.now(timezone.utc)
        age = (current_time - self.timestamp).total_seconds()
        return age > self.max_report_age_seconds or age < -1.0
