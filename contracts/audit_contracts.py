# contracts/audit_contracts.py
"""
Canonical Readiness Audit Contracts & Domain Models for NexTrade (Sub-Phase 4I).
Defines strongly typed, frozen dataclasses for 12 mandatory readiness check items (R1–R12),
provenance hashes, and authoritative readiness audit certificates.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class ReadinessAuditStatus(str, Enum):
    READY = "READY"
    HOLD = "HOLD"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ReadinessCheckItem:
    """
    Immutable observation record for a single readiness audit checkpoint (R1–R12).
    """
    check_id: str
    category: str
    name: str
    passed: bool
    details: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ReadinessAuditCertificate:
    """
    Authoritative Readiness Audit Certificate produced by LiveReadinessAuditor.
    Enforces Invariant 4I-P1: Readiness certification ONLY; zero live execution authorization.
    """
    audit_id: str
    promotion_certificate_id: str
    verified_evidence_hash: str
    git_release_stack: Dict[str, str]
    check_results: List[ReadinessCheckItem]
    audit_status: ReadinessAuditStatus
    audit_reasons: List[str] = field(default_factory=list)
    audit_hash: str = ""
    audited_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
