# tests/test_readiness_auditor.py
"""
Adversarial Readiness Audit Test Suite for NexTrade (Sub-Phase 4I).
Verifies:
1. READY decision when all 12 mandatory checkpoints (R1–R12) pass.
2. HOLD decision when audit is held pending manual review.
3. REJECT decision when any of the 12 audit checkpoints fails.
4. ProvenanceVerifier git release tag stack integrity.
5. Dual persistence in SQLite DB and JSONL audit trail.
"""
import os
import pytest
from datetime import datetime, timezone

from contracts.audit_contracts import ReadinessAuditStatus
from audit.provenance_verifier import ProvenanceVerifier
from audit.readiness_auditor import LiveReadinessAuditor
from audit.audit_reporter import AuditReporter
from storage.readiness_audit_store import ReadinessAuditStore


def test_readiness_auditor_ready_on_clean_audit():
    """Verify LiveReadinessAuditor returns READY when all 12 checkpoints pass cleanly."""
    auditor = LiveReadinessAuditor()
    cert = auditor.run_readiness_audit()

    assert cert.audit_status == ReadinessAuditStatus.READY
    assert len(cert.check_results) == 12
    assert all(c.passed for c in cert.check_results)
    assert len(cert.audit_hash) == 64  # SHA-256 hex string


def test_readiness_auditor_hold_decision():
    """Verify LiveReadinessAuditor returns HOLD when force_hold is requested."""
    auditor = LiveReadinessAuditor()
    cert = auditor.run_readiness_audit(force_hold=True)

    assert cert.audit_status == ReadinessAuditStatus.HOLD
    assert "HOLD" in cert.audit_reasons[0]


def test_readiness_auditor_reject_on_checkpoint_failure():
    """Verify LiveReadinessAuditor returns REJECT when a mandatory checkpoint fails."""
    auditor = LiveReadinessAuditor()

    # Fail checkpoint R3 (Safety Gate)
    cert_r3 = auditor.run_readiness_audit(force_reject_checkpoint="R3")
    assert cert_r3.audit_status == ReadinessAuditStatus.REJECT
    assert any("R3" in reason for reason in cert_r3.audit_reasons)

    # Fail checkpoint R10 (Configuration)
    cert_r10 = auditor.run_readiness_audit(force_reject_checkpoint="R10")
    assert cert_r10.audit_status == ReadinessAuditStatus.REJECT
    assert any("R10" in reason for reason in cert_r10.audit_reasons)


def test_provenance_verifier_git_tags():
    """Verify ProvenanceVerifier validates expected git release tags."""
    verifier = ProvenanceVerifier()
    is_valid, tag_map, errors = verifier.verify_git_release_stack()

    assert is_valid is True
    assert len(tag_map) == 9
    assert "v3.8-phase-4h-promotion-validation-complete" in tag_map


def test_readiness_store_and_reporter(tmp_path):
    """Verify ReadinessAuditStore saves certificates and AuditReporter generates reports."""
    auditor = LiveReadinessAuditor()
    cert = auditor.run_readiness_audit()

    db_path = str(tmp_path / "test_audit.db")
    jsonl_path = str(tmp_path / "test_audit.jsonl")
    store = ReadinessAuditStore(db_path=db_path, jsonl_path=jsonl_path)

    assert store.save_certificate(cert) is True
    assert os.path.exists(jsonl_path)

    md_report = AuditReporter.generate_markdown_certificate(cert)
    assert "Invariant 4I-P1 Notice" in md_report
    assert cert.audit_id in md_report
    assert "[R1]" in md_report

    json_report = AuditReporter.generate_json_certificate(cert)
    assert "audit_id" in json_report
