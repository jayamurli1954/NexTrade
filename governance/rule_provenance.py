"""
NexTrade Phase 5F — Rule Provenance & Preflight Certificate Logger.

Binds broker_rule_version, package_hash, signer_key_id, and session_epoch to immutable
preflight certificates and verifies epoch alignment during execution.
"""

import time
import hashlib
import json
import uuid
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from governance.secret_sanitizer import SecretSanitizer
from .signed_rule_validator import SignedRulePackage

logger = logging.getLogger("RuleProvenanceLogger")


class StaleCertificateException(Exception):
    """Raised when a preflight certificate is evaluated against an outdated session_epoch or rule_version."""
    pass


@dataclass
class RulePreflightCertificate:
    certificate_id: str
    broker_id: str
    account_id: str
    session_id: str
    session_epoch: int
    broker_rule_version: int
    rule_package_hash: str
    signer_key_id: str
    issued_at: float
    expires_at: float
    certificate_hash: str


class RuleProvenanceLogger:
    """
    Logger and verifier for rule provenance preflight certificates.
    """

    @staticmethod
    def compute_certificate_hash(
        certificate_id: str,
        broker_id: str,
        account_id: str,
        session_id: str,
        session_epoch: int,
        broker_rule_version: int,
        rule_package_hash: str,
        signer_key_id: str,
        issued_at: float,
        expires_at: float
    ) -> str:
        """Computes SHA-256 hash for preflight certificate payload."""
        payload = {
            "certificate_id": certificate_id,
            "broker_id": broker_id,
            "account_id": account_id,
            "session_id": session_id,
            "session_epoch": session_epoch,
            "broker_rule_version": broker_rule_version,
            "rule_package_hash": rule_package_hash,
            "signer_key_id": signer_key_id,
            "issued_at": round(issued_at, 3),
            "expires_at": round(expires_at, 3)
        }
        canonical_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(canonical_bytes).hexdigest()

    def create_preflight_certificate(
        self,
        broker_id: str,
        account_id: str,
        session_id: str,
        session_epoch: int,
        rule_package: SignedRulePackage,
        ttl_seconds: float = 300.0
    ) -> RulePreflightCertificate:
        """Creates an immutable preflight certificate."""
        cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires = now + ttl_seconds

        cert_hash = self.compute_certificate_hash(
            certificate_id=cert_id,
            broker_id=broker_id,
            account_id=account_id,
            session_id=session_id,
            session_epoch=session_epoch,
            broker_rule_version=rule_package.version,
            rule_package_hash=rule_package.package_hash,
            signer_key_id=rule_package.signer_key_id,
            issued_at=now,
            expires_at=expires
        )

        cert = RulePreflightCertificate(
            certificate_id=cert_id,
            broker_id=broker_id,
            account_id=account_id,
            session_id=session_id,
            session_epoch=session_epoch,
            broker_rule_version=rule_package.version,
            rule_package_hash=rule_package.package_hash,
            signer_key_id=rule_package.signer_key_id,
            issued_at=now,
            expires_at=expires,
            certificate_hash=cert_hash
        )
        logger.info("Created preflight certificate '%s' (Epoch: %d, Rule v%d)", cert_id, session_epoch, rule_package.version)
        return cert

    def verify_preflight_certificate(
        self,
        certificate: RulePreflightCertificate,
        active_session_epoch: int,
        active_rule_version: int
    ) -> bool:
        """
        Verifies preflight certificate validity, session_epoch alignment, and rule version alignment.
        """
        now = time.time()
        if now >= certificate.expires_at:
            err = f"Preflight certificate '{certificate.certificate_id}' is EXPIRED"
            logger.warning(err)
            raise StaleCertificateException(err)

        if certificate.session_epoch != active_session_epoch:
            err = f"Stale certificate session_epoch ({certificate.session_epoch} != active {active_session_epoch}). Revalidation required."
            logger.warning(err)
            raise StaleCertificateException(err)

        if certificate.broker_rule_version != active_rule_version:
            err = f"Stale certificate broker_rule_version ({certificate.broker_rule_version} != active {active_rule_version}). Revalidation required."
            logger.warning(err)
            raise StaleCertificateException(err)

        return True

    def get_sanitized_provenance_record(self, certificate: RulePreflightCertificate) -> Dict[str, Any]:
        """Returns sanitized dictionary for preflight certificate diagnostics."""
        raw = asdict(certificate)
        return SecretSanitizer.sanitize_dict(raw)
