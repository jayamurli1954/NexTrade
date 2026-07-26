"""
NexTrade Phase 5G — Multi-Account Preflight Certification Manager.

Enforces strict multi-account isolation, zero cross-account margin/position leakage,
and account-scoped preflight certificate validation.
"""

import logging
from typing import Dict, Any, Optional, Set

from governance.rule_provenance import RuleProvenanceLogger, RulePreflightCertificate, StaleCertificateException
from governance.signed_rule_validator import SignedRulePackage
from governance.secret_sanitizer import SecretSanitizer

logger = logging.getLogger("MultiAccountPreflightManager")


class CrossAccountViolationException(Exception):
    """Raised when an execution intent violates account isolation or attempts cross-account leakage."""
    pass


class MultiAccountPreflightManager:
    """
    Manager governing multi-account preflight certificate issuance, validation, and zero cross-account leakage.
    """

    def __init__(self, provenance_logger: Optional[RuleProvenanceLogger] = None) -> None:
        self.provenance_logger = provenance_logger or RuleProvenanceLogger()
        self._active_certificates: Dict[str, RulePreflightCertificate] = {}

    def issue_account_certificate(
        self,
        broker_id: str,
        account_id: str,
        session_id: str,
        session_epoch: int,
        rule_package: SignedRulePackage
    ) -> RulePreflightCertificate:
        """Issues an account-isolated preflight certificate."""
        cert = self.provenance_logger.create_preflight_certificate(
            broker_id=broker_id,
            account_id=account_id,
            session_id=session_id,
            session_epoch=session_epoch,
            rule_package=rule_package
        )
        cert_key = f"{broker_id}:{account_id}:{session_id}"
        self._active_certificates[cert_key] = cert
        logger.info("Issued multi-account preflight certificate for account '%s' (Broker: %s, Epoch: %d)", account_id, broker_id, session_epoch)
        return cert

    def validate_account_dispatch(
        self,
        order_payload: Dict[str, Any],
        certificate: RulePreflightCertificate,
        active_session_epoch: int,
        active_rule_version: int
    ) -> bool:
        """
        Validates account identity and zero cross-account leakage.
        """
        payload_account = str(order_payload.get("account_id", certificate.account_id))
        payload_broker = str(order_payload.get("broker_id", certificate.broker_id))

        # 1. Zero Cross-Account Leakage Assertion
        if payload_account != certificate.account_id:
            err = f"Cross-account isolation violation! Order account_id '{payload_account}' mismatch with certificate '{certificate.account_id}'"
            logger.critical(err)
            raise CrossAccountViolationException(err)

        if payload_broker != certificate.broker_id:
            err = f"Cross-account broker violation! Order broker_id '{payload_broker}' mismatch with certificate '{certificate.broker_id}'"
            logger.critical(err)
            raise CrossAccountViolationException(err)

        # 2. Session epoch and version alignment check
        return self.provenance_logger.verify_preflight_certificate(
            certificate=certificate,
            active_session_epoch=active_session_epoch,
            active_rule_version=active_rule_version
        )

    def get_sanitized_telemetry(self) -> Dict[str, Any]:
        """Returns sanitized telemetry for multi-account session monitoring."""
        telemetry = {
            "active_certificates_count": len(self._active_certificates),
            "accounts": list({c.account_id for c in self._active_certificates.values()})
        }
        return SecretSanitizer.sanitize_dict(telemetry)
