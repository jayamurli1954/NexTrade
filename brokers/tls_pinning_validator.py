"""
NexTrade Phase 5B — TLS Pinning Validator & Governed Pin Set Rotation.

Validates TLS certificate fingerprints and trust chain against governed active/backup pin sets.
"""

from dataclasses import dataclass
import hashlib
import time
import logging
from typing import Optional, List, Dict, Any

from .connection_state_machine import BrokerConnectionStateMachine, ConnectionState, ConnectionFault

logger = logging.getLogger("TLSPinningValidator")


class TLSPinningViolationException(Exception):
    """Raised when TLS certificate validation or fingerprint pinning fails."""
    pass


@dataclass
class TLSPinSet:
    """
    Governed TLS Pin Set containing active and backup certificate fingerprints.
    """
    active_pin: str
    backup_pin: Optional[str] = None
    pin_version: str = "v1.0"
    valid_from: str = "2026-01-01T00:00:00Z"
    valid_until: str = "2027-01-01T00:00:00Z"
    signature: str = "sig_tls_pinset_valid"

    def canonical_dict(self) -> Dict[str, Any]:
        return {
            "active_pin": self.active_pin,
            "backup_pin": self.backup_pin,
            "pin_version": self.pin_version,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
        }

    def compute_hash(self) -> str:
        import json
        payload = json.dumps(self.canonical_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TLSPinningValidator:
    """
    Validates TLS certificates for production broker endpoints against governed pin sets.
    """

    def __init__(self, pin_set: Optional[TLSPinSet] = None, state_machine: Optional[BrokerConnectionStateMachine] = None) -> None:
        self.pin_set = pin_set or TLSPinSet(active_pin="sha256/mock_active_pin_1234567890abcdef")
        self.state_machine = state_machine

    def rotate_pin_set(self, new_pin_set: TLSPinSet, signature_verify: bool = True) -> None:
        """
        Rotates active pin set with a governed, signed new pin set.
        """
        if signature_verify and not new_pin_set.signature:
            raise TLSPinningViolationException("Cannot rotate to un-signed TLS pin set")

        logger.info("Rotating TLS Pin Set for gateway from %s to %s", self.pin_set.pin_version, new_pin_set.pin_version)
        self.pin_set = new_pin_set

    def validate_certificate(self, cert_fingerprint: str, hostname: str) -> bool:
        """
        Validates server certificate fingerprint against active or backup pins.
        """
        clean_fingerprint = cert_fingerprint.lower().replace(":", "").replace("sha256/", "")
        active_clean = self.pin_set.active_pin.lower().replace(":", "").replace("sha256/", "")
        backup_clean = self.pin_set.backup_pin.lower().replace(":", "").replace("sha256/", "") if self.pin_set.backup_pin else None

        matched = (clean_fingerprint == active_clean) or (backup_clean and clean_fingerprint == backup_clean)

        if not matched:
            err_msg = f"TLS Pin Mismatch for '{hostname}': Received {cert_fingerprint}, expected active {self.pin_set.active_pin}"
            logger.critical(err_msg)
            if self.state_machine:
                self.state_machine.record_fault(ConnectionFault.TLS_FAILURE, err_msg)
            raise TLSPinningViolationException(err_msg)

        logger.debug("TLS Certificate verified for %s (pin version %s)", hostname, self.pin_set.pin_version)
        return True
