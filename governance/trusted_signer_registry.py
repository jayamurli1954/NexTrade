"""
NexTrade Phase 5F — Trusted Signer Key Registry.

Manages trusted signing keys, algorithms (Ed25519, ECDSA, HMAC-SHA256), key statuses,
and validity windows. Enforces 5F-S1 Secret Material Isolation for HMAC keys.
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from governance.secret_vault import SecretVault
from governance.secret_sanitizer import SecretSanitizer

logger = logging.getLogger("TrustedSignerRegistry")


class SignerKeyStatus(Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class SignerAlgorithm(Enum):
    ED25519 = "ED25519"
    ECDSA = "ECDSA"
    HMAC_SHA256 = "HMAC_SHA256"


class UntrustedSignerException(Exception):
    """Raised when a signing key is unknown, revoked, expired, or untrusted."""
    pass


@dataclass
class TrustedSigner:
    signer_key_id: str
    algorithm: SignerAlgorithm
    public_key: str
    status: SignerKeyStatus = SignerKeyStatus.ACTIVE
    valid_from: float = 0.0
    valid_until: float = 4102444800.0  # Default Far-future UTC timestamp (2100)


class TrustedSignerRegistry:
    """
    Registry of trusted signing keys with cryptographic material isolation.
    """

    def __init__(self, secret_vault: Optional[SecretVault] = None) -> None:
        self.secret_vault = secret_vault or SecretVault()
        self._signers: Dict[str, TrustedSigner] = {}

    def register_signer(
        self,
        signer_key_id: str,
        algorithm: SignerAlgorithm,
        public_key_or_secret_ref: str,
        status: SignerKeyStatus = SignerKeyStatus.ACTIVE,
        valid_from: float = 0.0,
        valid_until: float = 4102444800.0
    ) -> None:
        """
        Registers a trusted signer.
        5F-S1: For HMAC secrets, stores secret in SecretVault and sets public_key to '[VAULT_MANAGED]'.
        """
        if algorithm == SignerAlgorithm.HMAC_SHA256:
            # Store secret securely in vault
            self.secret_vault.store_secret(f"signer_key_{signer_key_id}", public_key_or_secret_ref)
            stored_key_repr = "[VAULT_MANAGED]"
        else:
            stored_key_repr = public_key_or_secret_ref

        signer = TrustedSigner(
            signer_key_id=signer_key_id,
            algorithm=algorithm,
            public_key=stored_key_repr,
            status=status,
            valid_from=valid_from,
            valid_until=valid_until
        )
        self._signers[signer_key_id] = signer
        logger.info("Registered trusted signer key '%s' (%s)", signer_key_id, algorithm.name)

    def revoke_signer(self, signer_key_id: str) -> None:
        """Revokes a trusted signer key."""
        if signer_key_id in self._signers:
            self._signers[signer_key_id].status = SignerKeyStatus.REVOKED
            logger.warning("Signer key '%s' has been REVOKED", signer_key_id)

    def get_verification_key(self, signer_key_id: str) -> str:
        """
        Retrieves the verification key for signature checking.
        HMAC secrets are retrieved from SecretVault, ensuring zero plain-text leakage in registry metadata.
        """
        signer = self.get_signer_metadata(signer_key_id)
        if signer.algorithm == SignerAlgorithm.HMAC_SHA256:
            return self.secret_vault.get_secret(f"signer_key_{signer_key_id}")
        return signer.public_key

    def get_signer_metadata(self, signer_key_id: str) -> TrustedSigner:
        """Retrieves signer metadata. Raises UntrustedSignerException if untrusted."""
        if signer_key_id not in self._signers:
            raise UntrustedSignerException(f"Signer key ID '{signer_key_id}' is unknown and untrusted")

        signer = self._signers[signer_key_id]
        if signer.status == SignerKeyStatus.REVOKED:
            raise UntrustedSignerException(f"Signer key ID '{signer_key_id}' is REVOKED")

        now = time.time()
        if now < signer.valid_from or now >= signer.valid_until:
            signer.status = SignerKeyStatus.EXPIRED
            raise UntrustedSignerException(f"Signer key ID '{signer_key_id}' is EXPIRED")

        return signer

    def get_sanitized_diagnostics(self) -> Dict[str, Any]:
        """Returns sanitized diagnostics dictionary ensuring zero key exposure."""
        diag = {
            "registered_signers_count": len(self._signers),
            "signers": {
                k: {
                    "algorithm": v.algorithm.name,
                    "status": v.status.name,
                    "public_key": SecretSanitizer.sanitize_text(v.public_key)
                }
                for k, v in self._signers.items()
            }
        }
        return SecretSanitizer.sanitize_dict(diag)
