# promotion/promotion_reporter.py
"""
Promotion Certification Reporter for NexTrade (Sub-Phase 4H).
Produces Markdown certificates and structured JSON reports for Phase 4I Live Readiness Audit.
"""
import json
from typing import Dict, Any

from contracts.promotion_contracts import PromotionDecisionRecord


class PromotionReporter:
    """
    Generates certification reports for downstream Phase 4I Live Readiness Audit.
    """

    @staticmethod
    def generate_markdown_certificate(record: PromotionDecisionRecord) -> str:
        """
        Generates a Markdown promotion certificate.
        """
        snap = record.evidence_snapshot
        lines = [
            f"# NexTrade Phase 4H — Promotion Certificate",
            f"**Certificate ID**: `{record.decision_id}`",
            f"**Decision Outcome**: `{record.decision.value}`",
            f"**Certified At**: `{record.approved_at.isoformat()}`",
            "",
            "## Cryptographic Evidence Provenance (Invariant 4H-P2)",
            f"- **Overall Snapshot Hash**: `{snap.evidence_snapshot_hash}`",
            f"- **Shadow Dataset Hash**: `{snap.shadow_dataset_hash}`",
            f"- **DLQ Snapshot Hash**: `{snap.dlq_snapshot_hash}`",
            f"- **Metrics Snapshot Hash**: `{snap.metrics_snapshot_hash}`",
            "",
            "## Core Pillar Evaluations",
            f"- **Safety Invariants (S1–S12)**: {'PASS' if record.safety_invariants_passed else 'FAIL'}",
            f"- **Event Integrity**: {'PASS' if record.event_integrity_passed else 'FAIL'}",
            f"- **Reconciliation Integrity**: {'PASS' if record.reconciliation_passed else 'FAIL'}",
            f"- **Observability & Alerts**: {'PASS' if record.observability_passed else 'FAIL'}",
            f"- **Empirical Performance**: {'PASS' if record.performance_thresholds_passed else 'FAIL'}",
            "",
            "## Empirical Metrics Summary",
            f"- **Total Shadow Orders**: {snap.total_shadow_orders}",
            f"- **Simulated Fill Rate**: {snap.simulated_fill_rate}%",
            f"- **Average Slippage**: {snap.average_slippage_bps} bps",
            f"- **Critical Alerts**: {snap.critical_alerts_count}",
            f"- **Unresolved Reconciliations**: {snap.unresolved_reconciliations_count}",
            "",
            "## Decision Reasons",
        ]
        for reason in record.decision_reasons:
            lines.append(f"- {reason}")

        lines.extend([
            "",
            "> [!IMPORTANT]",
            "> **Invariant 4H-P1 Notice**: This certificate certifies eligibility ONLY. It MUST NOT enable live trading, change environment, or dispatch broker orders.",
        ])

        return "\n".join(lines)

    @staticmethod
    def generate_json_certificate(record: PromotionDecisionRecord) -> str:
        """
        Generates a JSON formatted promotion certificate.
        """
        snap = record.evidence_snapshot
        data = {
            "certificate_id": record.decision_id,
            "decision": record.decision.value,
            "approved_at": record.approved_at.isoformat(),
            "provenance_hashes": {
                "evidence_snapshot_hash": snap.evidence_snapshot_hash,
                "shadow_dataset_hash": snap.shadow_dataset_hash,
                "dlq_snapshot_hash": snap.dlq_snapshot_hash,
                "metrics_snapshot_hash": snap.metrics_snapshot_hash,
            },
            "pillar_evaluations": {
                "safety_invariants_passed": record.safety_invariants_passed,
                "event_integrity_passed": record.event_integrity_passed,
                "reconciliation_passed": record.reconciliation_passed,
                "observability_passed": record.observability_passed,
                "performance_thresholds_passed": record.performance_thresholds_passed,
            },
            "metrics": {
                "total_shadow_orders": snap.total_shadow_orders,
                "simulated_fill_rate": snap.simulated_fill_rate,
                "average_slippage_bps": snap.average_slippage_bps,
                "critical_alerts_count": snap.critical_alerts_count,
                "unresolved_reconciliations_count": snap.unresolved_reconciliations_count,
            },
            "reasons": record.decision_reasons,
        }
        return json.dumps(data, indent=2)
