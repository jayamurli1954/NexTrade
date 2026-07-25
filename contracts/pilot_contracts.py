# contracts/pilot_contracts.py
"""
Canonical Controlled Live Pilot Contracts & Governance Models for NexTrade (Sub-Phase 4K).
Defines strongly typed, frozen dataclasses for pilot session configurations, pilot stages,
pre-flight certification, human order approvals, and operational evidence packages.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class PilotStage(str, Enum):
    STAGE_1_TINY_PILOT = "STAGE_1_TINY_PILOT"
    STAGE_2_SUPERVISED = "STAGE_2_SUPERVISED"
    STAGE_3_STAGING_BOUNDS = "STAGE_3_STAGING_BOUNDS"


@dataclass(frozen=True)
class PilotSessionConfig:
    """
    Immutable session configuration governing pilot execution bounds (Invariants 4K-P2, 4K-P5).
    """
    session_id: str
    pilot_stage: PilotStage = PilotStage.STAGE_1_TINY_PILOT
    max_daily_orders: int = 10
    max_cumulative_exposure: float = 2500.0
    max_daily_loss: float = 500.0
    max_concurrent_positions: int = 1
    approved_symbols: List[str] = field(default_factory=lambda: ["AAPL"])
    operator_id: str = "OP-PILOT-01"
    session_expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    config_hash: str = ""


@dataclass(frozen=True)
class PreflightCertificate:
    """
    Cryptographic certification produced by PreflightGate prior to session start (Invariant 4K-P3).
    """
    certificate_id: str
    session_id: str
    promo_4h_certificate_hash: str
    audit_4i_certificate_hash: str
    staging_4j_token_hash: str
    git_commit: str
    config_hash: str
    broker_endpoint_hash: str
    account_hash: str
    safety_gate_passed: bool
    reconciliation_passed: bool
    dlq_count: int
    critical_alerts_count: int
    evaluated_at: datetime
    preflight_evidence_hash: str


@dataclass(frozen=True)
class HumanOrderApproval:
    """
    Cryptographically traceable per-order human approval for Stage 1 (Invariant 4K-P4).
    """
    approval_id: str
    operator_id: str
    order_request_id: str
    symbol: str
    side: str
    approved_quantity: float
    approved_notional: float
    config_hash: str
    approved_at: datetime
    signature: str


@dataclass(frozen=True)
class PilotSessionRecord:
    """
    Immutable Operational Evidence Package generated upon pilot session close (Invariant 4K-P9).
    """
    session_id: str
    pilot_stage: PilotStage
    preflight_certificate_id: str
    total_orders: int
    filled_orders: int
    total_volume: float
    total_pnl: float
    average_slippage_bps: float
    reconciliation_clean: bool
    pilot_evidence_hash: str
    closed_at: datetime
