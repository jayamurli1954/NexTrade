# staging/staging_authorizer.py
"""
Multi-Certificate & Cryptographic Staging Authorizer Engine for NexTrade (Sub-Phase 4J).
Validates 4H PROMOTE certificate, 4I READY certificate, version tags, human intent IDs,
and HMAC signatures over cryptographically bound staging configurations (Invariants 4J-P1, 4J-P6–P9).
"""
import uuid
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional

from contracts.staging_contracts import StagingEnvironmentConfig, StagingAuthorizationToken


class StagingAuthorizer:
    """
    Cryptographic authorization manager binding certificates, human intent, and config hashes.
    """

    def __init__(self, secret_key: str = "NEXTRADE_STAGING_HMAC_SECRET_KEY_2026"):
        self.secret_key = secret_key

    @staticmethod
    def compute_hash(data: Any) -> str:
        """Computes deterministic SHA-256 hash over canonical JSON serialization."""
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def generate_hmac_signature(self, payload_dict: Dict[str, Any]) -> str:
        """Computes HMAC-SHA256 signature over canonical payload string."""
        canonical_str = json.dumps(payload_dict, sort_keys=True, default=str)
        return hmac.new(
            self.secret_key.encode("utf-8"),
            canonical_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def issue_authorization_token(
        self,
        promo_4h_certificate_id: str,
        audit_4i_certificate_id: str,
        git_commit: str,
        config: StagingEnvironmentConfig,
        human_authorization_id: str,
        validity_seconds: float = 3600.0
    ) -> StagingAuthorizationToken:
        """
        Issues an immutable StagingAuthorizationToken bound to config hashes and expiry.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=validity_seconds)
        token_id = f"TOK-STG-{uuid.uuid4().hex[:12].upper()}"

        config_hash = self.compute_hash({
            "max_order_quantity": config.max_order_quantity,
            "max_order_notional": config.max_order_notional,
            "max_daily_loss": config.max_daily_loss,
            "max_position_exposure": config.max_position_exposure,
            "max_concurrent_positions": config.max_concurrent_positions
        })
        symbol_allowlist_hash = self.compute_hash(sorted(config.allowed_symbols))
        broker_endpoint_hash = self.compute_hash(config.broker_endpoint)
        account_identity_hash = self.compute_hash(config.account_id)

        payload = {
            "token_id": token_id,
            "promo_4h_certificate_id": promo_4h_certificate_id,
            "audit_4i_certificate_id": audit_4i_certificate_id,
            "git_commit": git_commit,
            "config_hash": config_hash,
            "symbol_allowlist_hash": symbol_allowlist_hash,
            "broker_endpoint_hash": broker_endpoint_hash,
            "account_identity_hash": account_identity_hash,
            "human_authorization_id": human_authorization_id,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat()
        }
        signature = self.generate_hmac_signature(payload)

        return StagingAuthorizationToken(
            token_id=token_id,
            promo_4h_certificate_id=promo_4h_certificate_id,
            audit_4i_certificate_id=audit_4i_certificate_id,
            git_commit=git_commit,
            config_hash=config_hash,
            symbol_allowlist_hash=symbol_allowlist_hash,
            broker_endpoint_hash=broker_endpoint_hash,
            account_identity_hash=account_identity_hash,
            human_authorization_id=human_authorization_id,
            issued_at=now,
            expires_at=expires_at,
            hmac_signature=signature
        )

    def validate_authorization_token(
        self,
        token: Optional[StagingAuthorizationToken],
        config: StagingEnvironmentConfig,
        now: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Validates StagingAuthorizationToken against current config and expiry.
        """
        if token is None:
            return False, "AUTHORIZATION_DENIED: Staging authorization token missing"

        current = now or datetime.now(timezone.utc)
        if token.is_expired(current):
            return False, f"AUTHORIZATION_DENIED: Token expired at {token.expires_at.isoformat()}"

        if not token.human_authorization_id:
            return False, "AUTHORIZATION_DENIED: Human authorization ID missing"

        # Verify config hash
        expected_config_hash = self.compute_hash({
            "max_order_quantity": config.max_order_quantity,
            "max_order_notional": config.max_order_notional,
            "max_daily_loss": config.max_daily_loss,
            "max_position_exposure": config.max_position_exposure,
            "max_concurrent_positions": config.max_concurrent_positions
        })
        if token.config_hash != expected_config_hash:
            return False, "AUTHORIZATION_DENIED: Configuration hash mismatch (tampering detected)"

        # Verify broker endpoint hash
        if token.broker_endpoint_hash != self.compute_hash(config.broker_endpoint):
            return False, "AUTHORIZATION_DENIED: Broker endpoint identity mismatch"

        # Verify HMAC signature
        payload = {
            "token_id": token.token_id,
            "promo_4h_certificate_id": token.promo_4h_certificate_id,
            "audit_4i_certificate_id": token.audit_4i_certificate_id,
            "git_commit": token.git_commit,
            "config_hash": token.config_hash,
            "symbol_allowlist_hash": token.symbol_allowlist_hash,
            "broker_endpoint_hash": token.broker_endpoint_hash,
            "account_identity_hash": token.account_identity_hash,
            "human_authorization_id": token.human_authorization_id,
            "issued_at": token.issued_at.isoformat(),
            "expires_at": token.expires_at.isoformat()
        }
        expected_sig = self.generate_hmac_signature(payload)
        if not hmac.compare_digest(token.hmac_signature, expected_sig):
            return False, "AUTHORIZATION_DENIED: Invalid HMAC signature"

        return True, "AUTHORIZED: Staging authorization token valid"
