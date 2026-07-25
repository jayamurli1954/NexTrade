# observability/metrics_registry.py
"""
Telemetry Metrics Registry for NexTrade (Sub-Phase 4F).
Thread-safe metrics collection across 7 categories (SAFETY, GATEWAY, BROKER_SESSION,
EVENT_BUS, RECONCILIATION, DLQ, SYSTEM_HEALTH). Best-effort and failure-isolated.
"""
import threading
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from contracts.observability_contracts import (
    MetricRecord,
    MetricCategory,
    MetricType,
)


class MetricsRegistry:
    """
    Thread-safe, failure-isolated registry for counters, gauges, and histograms.
    """

    def __init__(self):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._records: List[MetricRecord] = []
        self._lock = threading.RLock()

    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def increment_counter(
        self,
        name: str,
        category: MetricCategory,
        amount: float = 1.0,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Best-effort counter increment. Swallows any internal error."""
        try:
            with self._lock:
                key = self._make_key(name, labels)
                self._counters[key] = self._counters.get(key, 0.0) + amount
                rec = MetricRecord(
                    name=name,
                    category=category,
                    metric_type=MetricType.COUNTER,
                    value=self._counters[key],
                    labels=labels or {},
                    timestamp=datetime.now(timezone.utc)
                )
                self._records.append(rec)
        except Exception:
            pass  # Failure-isolated: never crash caller

    def set_gauge(
        self,
        name: str,
        category: MetricCategory,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Best-effort gauge set. Swallows any internal error."""
        try:
            with self._lock:
                key = self._make_key(name, labels)
                self._gauges[key] = float(value)
                rec = MetricRecord(
                    name=name,
                    category=category,
                    metric_type=MetricType.GAUGE,
                    value=float(value),
                    labels=labels or {},
                    timestamp=datetime.now(timezone.utc)
                )
                self._records.append(rec)
        except Exception:
            pass

    def observe_histogram(
        self,
        name: str,
        category: MetricCategory,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Best-effort histogram observation. Swallows any internal error."""
        try:
            with self._lock:
                key = self._make_key(name, labels)
                if key not in self._histograms:
                    self._histograms[key] = []
                self._histograms[key].append(float(value))
                rec = MetricRecord(
                    name=name,
                    category=category,
                    metric_type=MetricType.HISTOGRAM,
                    value=float(value),
                    labels=labels or {},
                    timestamp=datetime.now(timezone.utc)
                )
                self._records.append(rec)
        except Exception:
            pass

    def get_snapshot(self) -> Dict[str, float]:
        """Returns snapshot dictionary of all current counter and gauge values."""
        try:
            with self._lock:
                snapshot = dict(self._counters)
                snapshot.update(self._gauges)
                for h_key, vals in self._histograms.items():
                    if vals:
                        snapshot[f"{h_key}_avg"] = sum(vals) / len(vals)
                        snapshot[f"{h_key}_count"] = float(len(vals))
                return snapshot
        except Exception:
            return {}

    def get_records(self) -> List[MetricRecord]:
        """Returns all recorded metric observations."""
        try:
            with self._lock:
                return list(self._records)
        except Exception:
            return []

    def clear(self) -> None:
        """Resets all metrics state."""
        try:
            with self._lock:
                self._counters.clear()
                self._gauges.clear()
                self._histograms.clear()
                self._records.clear()
        except Exception:
            pass
