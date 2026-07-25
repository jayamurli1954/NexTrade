# promotion/promotion_validator.py
"""
Core Promotion Validator Gate Engine for NexTrade (Sub-Phase 4H).
Evaluates empirical evidence snapshots against PromotionThresholds across 5 pillars.
Enforces decision precedence (REJECT > HOLD > PROMOTE), sticky safety failure rejection,
stale evidence rejection, and Invariant 4H-P1 (Certification eligibility ONLY).
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from contracts.promotion_contracts import (
    PromotionDecisionStatus,
    PromotionThresholds,
    PromotionEvidenceSnapshot,
    PromotionDecisionRecord,
)


class PromotionValidator:
    """
    Authoritative certification engine evaluating empirical shadow evidence for 4I promotion eligibility.
    """

    def __init__(self, thresholds: Optional[PromotionThresholds] = None):
        self.thresholds = thresholds or PromotionThresholds()

    def evaluate_promotion(
        self,
        snapshot: PromotionEvidenceSnapshot
    ) -> PromotionDecisionRecord:
        """
        Evaluates evidence snapshot against thresholds.
        Decision Precedence: REJECT > HOLD > PROMOTE.
        """
        now = datetime.now(timezone.utc)
        decision_id = f"CERT-PROM-{uuid.uuid4().hex[:12].upper()}"
        reasons: List[str] = []

        # Pillar 1 & 2: Mandatory Safety & Invariant Checks
        safety_passed = True
        if snapshot.unexpected_safety_failures > 0:
            safety_passed = False
            reasons.append(f"STICKY_REJECT: {snapshot.unexpected_safety_failures} unexpected safety gate failures occurred")

        # Reconciliation Check
        reconciliation_passed = True
        if snapshot.unresolved_reconciliations_count > self.thresholds.max_unresolved_reconciliations:
            reconciliation_passed = False
            reasons.append(f"STICKY_REJECT: {snapshot.unresolved_reconciliations_count} unresolved reconciliation items exist")

        # Observability & Alert Check
        observability_passed = True
        if snapshot.critical_alerts_count > self.thresholds.max_critical_alerts:
            observability_passed = False
            reasons.append(f"STICKY_REJECT: {snapshot.critical_alerts_count} critical/fatal alerts remain unacknowledged")

        # Performance Threshold Checks
        performance_passed = True
        if snapshot.total_shadow_orders >= self.thresholds.minimum_required_observations:
            if snapshot.simulated_fill_rate < self.thresholds.min_simulated_fill_rate:
                performance_passed = False
                reasons.append(f"REJECT: Simulated fill rate ({snapshot.simulated_fill_rate}%) below threshold ({self.thresholds.min_simulated_fill_rate}%)")
            if snapshot.average_slippage_bps > self.thresholds.max_allowed_slippage_bps:
                performance_passed = False
                reasons.append(f"REJECT: Average slippage ({snapshot.average_slippage_bps} bps) exceeds threshold ({self.thresholds.max_allowed_slippage_bps} bps)")

        event_integrity_passed = (snapshot.dlq_record_count == 0)

        # ----------------------------------------------------
        # DECISION EVALUATION PRECEDENCE: REJECT > HOLD > PROMOTE
        # ----------------------------------------------------

        # 1. Check for Mandatory REJECT Conditions
        if not safety_passed or not reconciliation_passed or not observability_passed or not performance_passed:
            decision = PromotionDecisionStatus.REJECT

        # 2. Check for HOLD Conditions (Stale Evidence or Insufficient Sample Size)
        elif snapshot.is_stale(self.thresholds.max_evidence_age_seconds, now):
            decision = PromotionDecisionStatus.HOLD
            reasons.append(f"HOLD: Evidence snapshot is stale or older than {self.thresholds.max_evidence_age_seconds} seconds")
        elif snapshot.total_shadow_orders < self.thresholds.minimum_required_observations:
            decision = PromotionDecisionStatus.HOLD
            reasons.append(
                f"HOLD: Insufficient shadow order sample size (INSUFFICIENT_EVIDENCE_SAMPLE_SIZE: {snapshot.total_shadow_orders} < minimum required {self.thresholds.minimum_required_observations})"
            )

        # 3. Clean Pass -> PROMOTE Eligibility Certification
        else:
            decision = PromotionDecisionStatus.PROMOTE
            reasons.append("PROMOTE: All 5 core pillars passed cleanly with sufficient empirical evidence")

        evidence_references = {
            "snapshot_id": snapshot.snapshot_id,
            "evidence_snapshot_hash": snapshot.evidence_snapshot_hash,
            "shadow_dataset_hash": snapshot.shadow_dataset_hash,
            "dlq_snapshot_hash": snapshot.dlq_snapshot_hash,
            "metrics_snapshot_hash": snapshot.metrics_snapshot_hash,
        }

        return PromotionDecisionRecord(
            decision_id=decision_id,
            evidence_snapshot=snapshot,
            safety_invariants_passed=safety_passed,
            event_integrity_passed=event_integrity_passed,
            reconciliation_passed=reconciliation_passed,
            observability_passed=observability_passed,
            performance_thresholds_passed=performance_passed,
            decision=decision,
            decision_reasons=reasons,
            evidence_references=evidence_references,
            approved_at=now
        )
