# contracts/resilience_contracts.py
"""
Canonical Operational Resilience Contracts & Incident Models for NexTrade (Sub-Phase 4L).
Defines strongly typed, frozen dataclasses for incidents, chaos drill results, recovery epochs,
and authoritative operational resilience certificates.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class ResilienceCertificateStatus(str, Enum):
    READY = "READY"
    HOLD = "HOLD"
    REJECT = "REJECT"


@dataclass(frozen=True)
class IncidentRecord:
    """
    Immutable observation record capturing system incidents and fail-closed responses.
    """
    incident_id: str
    subsystem: str
    severity: IncidentSeverity
    description: str
    triggered_action: str  # HARD_HALT, REDUCE_ONLY, RECONCILIATION_LOCK
    operator_acknowledged: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ChaosDrillResult:
    """
    Certified result for an individual operational resilience chaos drill (Invariant 4L-P11).
    """
    drill_id: str
    precondition: str
    fault_injected: str
    expected_state: str
    actual_state: str
    orders_blocked: bool
    passed: bool
    evidence_hash: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ResilienceCertificate:
    """
    Authoritative Operational Resilience Certificate produced by ChaosRunner (Invariant 4L-P13).
    Enforces Invariant 4L-P4: Certification eligibility ONLY; zero execution authorization.
    """
    certificate_id: str
    pilot_session_id: str
    recovery_epoch: int
    drills_passed_count: int
    incident_recovery_passed: bool
    status: ResilienceCertificateStatus
    reasons: List[str] = field(default_factory=list)
    evidence_hash: str = ""
    certified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
