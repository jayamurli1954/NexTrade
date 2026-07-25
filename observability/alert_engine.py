# observability/alert_engine.py
"""
Alerting Engine & Incident Dispatcher for NexTrade (Sub-Phase 4F).
Evaluates metric thresholds, creates structured AlertRecord items with explicit severity,
condition, threshold, and recommended actions, and dispatches to registered handlers.
Failure-isolated and read-only.
"""
import uuid
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Callable, Optional

from contracts.observability_contracts import AlertLevel, AlertRecord


class AlertEngine:
    """
    Evaluates incident alert conditions and dispatches explicit AlertRecords to listeners.
    """

    def __init__(self):
        self._alerts: List[AlertRecord] = []
        self._handlers: List[Callable[[AlertRecord], None]] = []
        self._lock = threading.RLock()

    def register_handler(self, handler: Callable[[AlertRecord], None]) -> None:
        """Registers a downstream alert notification handler callback."""
        with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    def trigger_alert(
        self,
        severity: AlertLevel,
        source_subsystem: str,
        condition: str,
        threshold: str,
        recommended_action: str,
        metrics_snapshot: Optional[Dict[str, Any]] = None
    ) -> AlertRecord:
        """
        Creates and dispatches an explicit AlertRecord.
        Failure-isolated: Swallows exceptions from downstream handlers.
        """
        now = datetime.now(timezone.utc)
        alert_id = f"ALT-{uuid.uuid4().hex[:12].upper()}"

        record = AlertRecord(
            alert_id=alert_id,
            severity=severity,
            source_subsystem=source_subsystem,
            condition=condition,
            threshold=threshold,
            recommended_action=recommended_action,
            metrics_snapshot=metrics_snapshot or {},
            timestamp=now
        )

        with self._lock:
            self._alerts.append(record)
            handlers_copy = list(self._handlers)

        # Dispatch to registered handlers (best-effort)
        for handler in handlers_copy:
            try:
                handler(record)
            except Exception:
                pass  # Failure-isolated: never crash core execution

        return record

    def evaluate_thresholds(self, snapshot: Dict[str, Any]) -> List[AlertRecord]:
        """
        Evaluates metrics snapshot against predefined threshold rules.
        """
        new_alerts: List[AlertRecord] = []

        try:
            # Rule 1: Broker Connection Disconnect
            conn_status = snapshot.get("broker_connection_status")
            if conn_status == "DISCONNECTED":
                new_alerts.append(
                    self.trigger_alert(
                        severity=AlertLevel.CRITICAL,
                        source_subsystem="BROKER_SESSION",
                        condition="Broker socket connection is DISCONNECTED",
                        threshold="status == CONNECTED",
                        recommended_action="Check network connectivity and IBKR gateway status; trigger reconciliation",
                        metrics_snapshot=snapshot
                    )
                )

            # Rule 2: High Daily Loss Breach (> 80% limit)
            daily_loss = snapshot.get("daily_loss", 0.0)
            max_loss = snapshot.get("max_daily_loss", 5000.0)
            if max_loss > 0 and daily_loss >= 0.8 * max_loss:
                sev = AlertLevel.FATAL if daily_loss >= max_loss else AlertLevel.WARNING
                new_alerts.append(
                    self.trigger_alert(
                        severity=sev,
                        source_subsystem="SAFETY_GATE",
                        condition=f"Daily loss ({daily_loss}) reached 80%+ of maximum limit ({max_loss})",
                        threshold=f"daily_loss < 0.8 * {max_loss}",
                        recommended_action="Review active strategy risks and consider manual KillSwitch activation",
                        metrics_snapshot=snapshot
                    )
                )

            # Rule 3: DLQ Spike (> 10 records)
            dlq_count = snapshot.get("dlq_count", 0)
            if dlq_count > 10:
                new_alerts.append(
                    self.trigger_alert(
                        severity=AlertLevel.WARNING,
                        source_subsystem="DLQ",
                        condition=f"Dead-Letter Queue record count ({dlq_count}) exceeds threshold",
                        threshold="dlq_count <= 10",
                        recommended_action="Inspect DLQ records for out-of-order sequence gaps or corrupt payloads",
                        metrics_snapshot=snapshot
                    )
                )

            # Rule 4: Un-reconciled Orders Detected
            unreconciled = snapshot.get("unreconciled_orders", 0)
            if unreconciled > 0:
                new_alerts.append(
                    self.trigger_alert(
                        severity=AlertLevel.CRITICAL,
                        source_subsystem="RECONCILIATION",
                        condition=f"Un-reconciled active orders detected: {unreconciled}",
                        threshold="unreconciled_orders == 0",
                        recommended_action="Run reconciliation authority review key resolution",
                        metrics_snapshot=snapshot
                    )
                )

        except Exception:
            pass

        return new_alerts

    def get_alerts(self) -> List[AlertRecord]:
        """Returns all generated AlertRecords."""
        with self._lock:
            return list(self._alerts)

    def clear(self) -> None:
        """Clears stored alerts."""
        with self._lock:
            self._alerts.clear()
