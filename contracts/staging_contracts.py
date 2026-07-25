# contracts/staging_contracts.py
"""
Canonical Controlled Live Staging Contracts & Domain Models for NexTrade (Sub-Phase 4J).
Defines strongly typed, frozen dataclasses for staging environment limits,
human intent authorization tokens, cryptographic binding hashes, and full order lineage.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class StagingEnvironmentConfig:
    """
    Immutable configuration parameters governing Controlled Live Staging bounds.
    """
    max_order_quantity: float = 10.0
    max_order_notional: float = 1000.0
    max_daily_loss: float = 500.0
    max_position_exposure: float = 2500.0
    max_concurrent_positions: int = 2
    allowed_symbols: List[str] = field(default_factory=lambda: ["AAPL", "MSFT"])
    broker_endpoint: str = "127.0.0.1:7497"
    account_id: str = "DU123456"
    config_hash: str = ""


@dataclass(frozen=True)
class StagingAuthorizationToken:
    """
    Cryptographically bound authorization token binding 4H, 4I, human intent, and config hashes (Invariant 4J-P6).
    """
    token_id: str
    promo_4h_certificate_id: str
    audit_4i_certificate_id: str
    git_commit: str
    config_hash: str
    symbol_allowlist_hash: str
    broker_endpoint_hash: str
    account_identity_hash: str
    human_authorization_id: str
    issued_at: datetime
    expires_at: datetime
    hmac_signature: str

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Returns True if current time is past expires_at (Invariant 4J-P7)."""
        current = now or datetime.now(timezone.utc)
        return current > self.expires_at


@dataclass(frozen=True)
class StagingOrderLineage:
    """
    Complete end-to-end immutable correlation lineage for staging orders (Invariant 4J-P5).
    """
    staging_id: str
    correlation_id: str
    signal_id: str
    risk_decision_id: str
    execution_request_id: str
    promo_4h_certificate_id: str
    audit_4i_certificate_id: str
    authorization_token_id: str
    config_hash: str
    broker_endpoint_hash: str
    safety_gate_result: str
    staging_gate_result: str
    circuit_breaker_state: str
    kill_switch_state: str
    broker_order_id: str
    broker_status: str
    reconciliation_status: str
    timestamps: Dict[str, datetime] = field(default_factory=dict)


@dataclass(frozen=True)
class StagingGateResult:
    """
    Result of a StagingGate authorization evaluation.
    """
    authorized: bool
    reason: str
    lineage: Optional[StagingOrderLineage] = None
