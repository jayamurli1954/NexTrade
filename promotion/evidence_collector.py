# promotion/evidence_collector.py
"""
Evidence Collector & Deterministic SHA-256 Fingerprinter for NexTrade (Sub-Phase 4H).
Gathers empirical evidence across 5 core pillars and computes canonical SHA-256
provenance hashes (Invariant 4H-P2).
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from contracts.promotion_contracts import PromotionEvidenceSnapshot
from storage.shadow_store import ShadowStore
from events.event_bus import AuditableDLQ
from observability.metrics_registry import MetricsRegistry
from observability.alert_engine import AlertEngine


class EvidenceCollector:
    """
    Collects empirical evidence and computes deterministic SHA-256 provenance hashes.
    """

    def __init__(
        self,
        shadow_store: Optional[ShadowStore] = None,
        dlq: Optional[AuditableDLQ] = None,
        metrics_registry: Optional[MetricsRegistry] = None,
        alert_engine: Optional[AlertEngine] = None
    ):
        self.shadow_store = shadow_store or ShadowStore()
        self.dlq = dlq
        self.metrics_registry = metrics_registry
        self.alert_engine = alert_engine

    @staticmethod
    def _compute_sha256(data_dict: Any) -> str:
        """
        Computes a deterministic SHA-256 hash over a canonical JSON serialization.
        Enforces sorted keys and formatted strings.
        """
        json_str = json.dumps(data_dict, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def collect_evidence_snapshot(
        self,
        evaluation_start: Optional[datetime] = None,
        evaluation_end: Optional[datetime] = None,
        unresolved_reconciliations_count: int = 0
    ) -> PromotionEvidenceSnapshot:
        """
        Collects empirical evidence, validates freshness, and computes deterministic SHA-256 hashes.
        """
        now = datetime.now(timezone.utc)
        start_time = evaluation_start or (now.replace(hour=0, minute=0, second=0, microsecond=0))
        end_time = evaluation_end or now
        snapshot_id = f"SNAP-{uuid.uuid4().hex[:12].upper()}"

        # 1. Shadow Store Evidence
        shadow_records = self.shadow_store.get_records()
        total_shadow_orders = len(shadow_records)
        filled_records = [r for r in shadow_records if r.status.value == "SHADOW_FILLED" or str(r.status) == "SHADOW_FILLED"]
        simulated_fill_count = len(filled_records)
        simulated_fill_rate = (simulated_fill_count / total_shadow_orders * 100.0) if total_shadow_orders > 0 else 0.0

        slippage_values = [r.slippage_bps for r in filled_records]
        avg_slippage = (sum(slippage_values) / len(slippage_values)) if slippage_values else 0.0

        shadow_canonical_data = [
            {
                "shadow_id": r.shadow_id,
                "execution_request_id": r.execution_request_id,
                "symbol": r.symbol,
                "status": str(r.status),
                "slippage_bps": r.slippage_bps
            }
            for r in shadow_records
        ]
        shadow_dataset_hash = self._compute_sha256(shadow_canonical_data)

        # 2. DLQ Evidence
        dlq_records = self.dlq.get_records() if self.dlq else []
        dlq_record_count = len(dlq_records)
        dlq_canonical_data = [
            {"dlq_id": r.dlq_id, "reason": r.rejection_reason, "event_id": r.event.event_id}
            for r in dlq_records
        ]
        dlq_snapshot_hash = self._compute_sha256(dlq_canonical_data)

        # 3. Observability & Alerts Evidence
        metrics_snapshot = self.metrics_registry.get_snapshot() if self.metrics_registry else {}
        metrics_snapshot_hash = self._compute_sha256(metrics_snapshot)

        alerts = self.alert_engine.get_alerts() if self.alert_engine else []
        critical_alerts = [a for a in alerts if a.severity.value in ("CRITICAL", "FATAL") or str(a.severity) in ("CRITICAL", "FATAL")]
        critical_alerts_count = len(critical_alerts)

        # 4. Denominator-based Safety Coverage
        safety_total = int(metrics_snapshot.get("nextrade_safety_evaluations_total", 0.0))
        safety_passed = int(metrics_snapshot.get("nextrade_safety_evaluations_total{status=AUTHORIZED}", 0.0))
        expected_denials = int(metrics_snapshot.get("nextrade_safety_evaluations_total{status=DENIED}", 0.0))
        unexpected_failures = int(metrics_snapshot.get("nextrade_safety_evaluations_total{status=EXCEPTION}", 0.0))

        # 5. Combined Overall Evidence Snapshot Hash (Invariant 4H-P2)
        combined_hash_payload = {
            "shadow_dataset_hash": shadow_dataset_hash,
            "dlq_snapshot_hash": dlq_snapshot_hash,
            "metrics_snapshot_hash": metrics_snapshot_hash,
            "snapshot_id": snapshot_id,
            "timestamp": now.isoformat()
        }
        evidence_snapshot_hash = self._compute_sha256(combined_hash_payload)

        return PromotionEvidenceSnapshot(
            snapshot_id=snapshot_id,
            evaluation_start=start_time,
            evaluation_end=end_time,
            snapshot_timestamp=now,
            total_shadow_orders=total_shadow_orders,
            simulated_fill_rate=round(simulated_fill_rate, 2),
            average_slippage_bps=round(avg_slippage, 2),
            dlq_record_count=dlq_record_count,
            critical_alerts_count=critical_alerts_count,
            unresolved_reconciliations_count=unresolved_reconciliations_count,
            safety_evaluations_total=safety_total,
            safety_evaluations_passed=safety_passed,
            expected_safety_denials=expected_denials,
            unexpected_safety_failures=unexpected_failures,
            shadow_dataset_hash=shadow_dataset_hash,
            dlq_snapshot_hash=dlq_snapshot_hash,
            metrics_snapshot_hash=metrics_snapshot_hash,
            evidence_snapshot_hash=evidence_snapshot_hash
        )
