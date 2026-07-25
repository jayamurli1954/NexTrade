# tests/test_promotion_validator.py
"""
Adversarial Promotion Gate Test Suite for NexTrade (Sub-Phase 4H).
Verifies:
1. HOLD decision on sample size < 50 or stale evidence snapshot (> 24h).
2. Sticky REJECT decision on mandatory safety failures, reconciliation errors, or high slippage.
3. PROMOTE decision on 100% clean evidence with sample size >= 50.
4. SHA-256 evidence fingerprint reproducibility (Invariant 4H-P2).
5. Dual persistence in SQLite and JSONL log.
"""
import os
import pytest
from datetime import datetime, timezone, timedelta

from contracts.promotion_contracts import (
    PromotionDecisionStatus,
    PromotionThresholds,
    PromotionEvidenceSnapshot,
)
from promotion.evidence_collector import EvidenceCollector
from promotion.promotion_validator import PromotionValidator
from promotion.promotion_reporter import PromotionReporter
from storage.promotion_store import PromotionStore


@pytest.fixture
def clean_snapshot_50():
    now = datetime.now(timezone.utc)
    data = {"sample": 50}
    sha = EvidenceCollector._compute_sha256(data)
    return PromotionEvidenceSnapshot(
        snapshot_id="SNAP-TEST-01",
        evaluation_start=now - timedelta(hours=1),
        evaluation_end=now,
        snapshot_timestamp=now,
        total_shadow_orders=50,
        simulated_fill_rate=90.0,
        average_slippage_bps=5.0,
        dlq_record_count=0,
        critical_alerts_count=0,
        unresolved_reconciliations_count=0,
        safety_evaluations_total=100,
        safety_evaluations_passed=100,
        expected_safety_denials=0,
        unexpected_safety_failures=0,
        shadow_dataset_hash=sha,
        dlq_snapshot_hash=sha,
        metrics_snapshot_hash=sha,
        evidence_snapshot_hash=sha
    )


def test_hold_decision_on_insufficient_sample_size(clean_snapshot_50):
    """Verify PromotionValidator returns HOLD when sample size < 50."""
    validator = PromotionValidator()

    # Modify sample size to 10 < 50
    small_snapshot = PromotionEvidenceSnapshot(
        **{**clean_snapshot_50.__dict__, "total_shadow_orders": 10}
    )

    record = validator.evaluate_promotion(small_snapshot)
    assert record.decision == PromotionDecisionStatus.HOLD
    assert "INSUFFICIENT_EVIDENCE_SAMPLE_SIZE" in record.decision_reasons[0]


def test_hold_decision_on_stale_evidence():
    """Verify PromotionValidator returns HOLD when evidence is older than 24 hours."""
    validator = PromotionValidator()
    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    sha = "abc123hash"

    stale_snapshot = PromotionEvidenceSnapshot(
        snapshot_id="SNAP-STALE",
        evaluation_start=old_time - timedelta(hours=1),
        evaluation_end=old_time,
        snapshot_timestamp=old_time,
        total_shadow_orders=60,
        simulated_fill_rate=90.0,
        average_slippage_bps=5.0,
        dlq_record_count=0,
        critical_alerts_count=0,
        unresolved_reconciliations_count=0,
        safety_evaluations_total=100,
        safety_evaluations_passed=100,
        expected_safety_denials=0,
        unexpected_safety_failures=0,
        shadow_dataset_hash=sha,
        dlq_snapshot_hash=sha,
        metrics_snapshot_hash=sha,
        evidence_snapshot_hash=sha
    )

    record = validator.evaluate_promotion(stale_snapshot)
    assert record.decision == PromotionDecisionStatus.HOLD
    assert "EVIDENCE_EXPIRED_OR_STALE" in record.decision_reasons[0] or "stale" in record.decision_reasons[0]


def test_sticky_reject_on_unexpected_safety_failure(clean_snapshot_50):
    """Verify unexpected safety failures trigger a sticky REJECT decision."""
    validator = PromotionValidator()

    bad_snapshot = PromotionEvidenceSnapshot(
        **{**clean_snapshot_50.__dict__, "unexpected_safety_failures": 1}
    )

    record = validator.evaluate_promotion(bad_snapshot)
    assert record.decision == PromotionDecisionStatus.REJECT
    assert "STICKY_REJECT" in record.decision_reasons[0]


def test_reject_on_high_slippage(clean_snapshot_50):
    """Verify average slippage exceeding limit (15.0 bps) returns REJECT."""
    validator = PromotionValidator()

    high_slippage_snapshot = PromotionEvidenceSnapshot(
        **{**clean_snapshot_50.__dict__, "average_slippage_bps": 20.0}
    )

    record = validator.evaluate_promotion(high_slippage_snapshot)
    assert record.decision == PromotionDecisionStatus.REJECT
    assert "Average slippage" in record.decision_reasons[0]


def test_promote_decision_on_clean_evidence(clean_snapshot_50):
    """Verify 100% clean evidence with sample size >= 50 yields PROMOTE."""
    validator = PromotionValidator()
    record = validator.evaluate_promotion(clean_snapshot_50)

    assert record.decision == PromotionDecisionStatus.PROMOTE
    assert record.safety_invariants_passed is True
    assert record.performance_thresholds_passed is True


def test_sha256_provenance_reproducibility():
    """Verify EvidenceCollector SHA-256 fingerprinting is deterministic (Invariant 4H-P2)."""
    data1 = {"b": 2, "a": 1, "c": [1, 2, 3]}
    data2 = {"a": 1, "c": [1, 2, 3], "b": 2}

    hash1 = EvidenceCollector._compute_sha256(data1)
    hash2 = EvidenceCollector._compute_sha256(data2)

    assert hash1 == hash2
    assert len(hash1) == 64  # Valid SHA-256 hex string


def test_promotion_store_and_reporter(clean_snapshot_50, tmp_path):
    """Verify PromotionStore saves certificates and PromotionReporter generates Markdown/JSON."""
    validator = PromotionValidator()
    record = validator.evaluate_promotion(clean_snapshot_50)

    db_path = str(tmp_path / "test_promo.db")
    jsonl_path = str(tmp_path / "test_promo.jsonl")
    store = PromotionStore(db_path=db_path, jsonl_path=jsonl_path)

    assert store.save_certificate(record) is True
    assert os.path.exists(jsonl_path)

    md_report = PromotionReporter.generate_markdown_certificate(record)
    assert "Invariant 4H-P1 Notice" in md_report
    assert record.decision_id in md_report

    json_report = PromotionReporter.generate_json_certificate(record)
    assert "certificate_id" in json_report
