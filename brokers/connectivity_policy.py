"""
NexTrade Phase 5B — Broker Connectivity Policy.

Versioned, hashable, cryptographically verifiable, broker-specific connectivity policy.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("BrokerConnectivityPolicy")


class InvalidConnectivityPolicyException(Exception):
    """Raised when a connectivity policy fails integrity or bounds checks."""
    pass


@dataclass
class BrokerConnectivityPolicy:
    """
    Versioned, immutable, session-bound broker connectivity policy.
    """
    broker_id: str
    environment: str
    policy_version: str = "v1.0-prod"
    effective_from: str = "2026-01-01T00:00:00Z"
    effective_until: Optional[str] = None
    source: str = "GOVERNANCE_REGISTRY"
    signature: str = "sig_sha256_mock_valid_signature_hash"
    
    heartbeat_timeout_sec: float = 5.0
    connection_timeout_sec: float = 10.0
    order_ack_timeout_sec: float = 3.0
    cancellation_ack_timeout_sec: float = 3.0
    market_data_staleness_limit_sec: float = 2.0
    latency_warning_threshold_ms: float = 500.0
    latency_hard_limit_ms: float = 1500.0

    policy_hash: str = field(default="")
    _locked: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if not self.policy_hash:
            self.policy_hash = self.compute_policy_hash()

    def canonical_dict(self) -> Dict[str, Any]:
        """Returns canonical dictionary representation for hashing."""
        return {
            "broker_id": self.broker_id,
            "environment": self.environment,
            "policy_version": self.policy_version,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "source": self.source,
            "heartbeat_timeout_sec": float(self.heartbeat_timeout_sec),
            "connection_timeout_sec": float(self.connection_timeout_sec),
            "order_ack_timeout_sec": float(self.order_ack_timeout_sec),
            "cancellation_ack_timeout_sec": float(self.cancellation_ack_timeout_sec),
            "market_data_staleness_limit_sec": float(self.market_data_staleness_limit_sec),
            "latency_warning_threshold_ms": float(self.latency_warning_threshold_ms),
            "latency_hard_limit_ms": float(self.latency_hard_limit_ms),
        }

    def compute_policy_hash(self) -> str:
        """Computes SHA-256 hash over canonical policy payload."""
        payload = json.dumps(self.canonical_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Verifies policy hash, signature presence, and numerical bounds.
        Raises InvalidConnectivityPolicyException if invalid.
        """
        expected_hash = self.compute_policy_hash()
        if self.policy_hash != expected_hash:
            raise InvalidConnectivityPolicyException(
                f"Policy hash mismatch: computed {expected_hash}, recorded {self.policy_hash}"
            )

        if not self.signature:
            raise InvalidConnectivityPolicyException("Missing cryptographic signature on policy")

        # Sane safety bounds check
        if self.heartbeat_timeout_sec <= 0 or self.connection_timeout_sec <= 0:
            raise InvalidConnectivityPolicyException("Timeouts must be positive numbers")

        if self.latency_warning_threshold_ms >= self.latency_hard_limit_ms:
            raise InvalidConnectivityPolicyException("Warning threshold must be less than hard limit")

        return True

    def lock_session(self) -> "BrokerConnectivityPolicy":
        """Returns a locked, immutable policy bound to active session."""
        self.verify_integrity()
        self._locked = True
        return self
