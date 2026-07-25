# contracts/promotion_contracts.py
"""
Canonical Promotion Gate Contracts & Domain Models for NexTrade (Sub-Phase 4H).
Defines strongly typed, frozen dataclasses for evidence snapshots, deterministic SHA-256
fingerprints, promotion thresholds, and authoritative decision certificates.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class PromotionDecisionStatus(str, Enum):
    PROMOTE = "PROMOTE"
    HOLD = "HOLD"
    REJECT = "REJECT"


@dataclass(frozen=True)
class PromotionThresholds:
    """
    Configurable eligibility thresholds for Shadow Mode promotion gating.
    """
    minimum_required_observations: int = 50
    min_simulated_fill_rate: float = 80.0
    max_allowed_slippage_bps: float = 15.0
    max_allowed_dlq_rate: float = 1.0
    max_unresolved_reconciliations: int = 0
    max_critical_alerts: int = 0
    max_evidence_age_seconds: float = 86400.0  # 24 hours maximum evidence age


@dataclass(frozen=True)
class PromotionEvidenceSnapshot:
    """
    Immutable point-in-time evidence snapshot with deterministic SHA-256 fingerprints.
    """
    snapshot_id: str
    evaluation_start: datetime
    evaluation_end: datetime
    snapshot_timestamp: datetime
    total_shadow_orders: int
    simulated_fill_rate: float
    average_slippage_bps: float
    dlq_record_count: int
    critical_alerts_count: int
    unresolved_reconciliations_count: int
    safety_evaluations_total: int
    safety_evaluations_passed: int
    expected_safety_denials: int
    unexpected_safety_failures: int
    shadow_dataset_hash: str
    dlq_snapshot_hash: str
    metrics_snapshot_hash: str
    evidence_snapshot_hash: str

    def is_stale(self, max_age_seconds: float = 86400.0, now: Optional[datetime] = None) -> bool:
        """Returns True if snapshot timestamp is older than max_age_seconds."""
        current_time = now or datetime.now(timezone.utc)
        age = (current_time - self.snapshot_timestamp).total_seconds()
        return age > max_age_seconds or age < -1.0


@dataclass(frozen=True)
class PromotionDecisionRecord:
    """
    Authoritative Promotion Decision Certificate produced by PromotionValidator.
    Enforces Invariant 4H-P1: Certification eligibility ONLY; zero execution authorization.
    """
    decision_id: str
    evidence_snapshot: PromotionEvidenceSnapshot
    safety_invariants_passed: bool
    event_integrity_passed: bool
    reconciliation_passed: bool
    observability_passed: bool
    performance_thresholds_passed: bool
    decision: PromotionDecisionStatus
    decision_reasons: List[str] = field(default_factory=list)
    evidence_references: Dict[str, str] = field(default_factory=dict)
    approved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
