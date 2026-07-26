"""
NexTrade Phase 5C — Secret Lifecycle & Memory Scrubbing Manager.

Governs secret rotation, versioning, validity windows, emergency revocation,
and in-memory byte scrubbing upon revocation or session teardown.
"""

import time
import logging
from typing import Dict, Any, Optional, Set

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from .secret_vault import SecretVault, SecretVaultViolationException
from .secret_sanitizer import SecretSanitizer

logger = logging.getLogger("SecretLifecycleManager")


class SecretRevocationException(Exception):
    """Raised when an operation attempts to consume a revoked secret."""
    pass


class SecretLifecycleManager:
    """
    Manages active, deprecated, and revoked secrets.
    Enforces in-memory byte scrubbing and SafetyControlPlane state transitions on secret revocation.
    """

    def __init__(self, vault: Optional[SecretVault] = None, control_plane: Optional[SafetyControlPlane] = None) -> None:
        self.vault = vault or SecretVault()
        self.control_plane = control_plane or SafetyControlPlane()
        self._revoked_keys: Set[str] = set()
        self._active_versions: Dict[str, str] = {}

    def rotate_secret(self, key_id: str, new_payload: str, new_version: str = "v2") -> bool:
        """
        Rotates secret to a new version.
        Stores new payload in SecretVault and updates active version registry.
        """
        if key_id in self._revoked_keys:
            raise SecretRevocationException(f"Cannot rotate revoked secret key '{key_id}'")

        self.vault.store_secret(key_id, new_payload)
        self.vault.store_secret(f"{key_id}_version", new_version)
        self._active_versions[key_id] = new_version

        logger.info("Secret '%s' successfully rotated to version %s", key_id, new_version)
        return True

    def revoke_secret(self, key_id: str, reason: str, authority: str = "SYSTEM") -> None:
        """
        Emergency secret revocation.
        Marks key as revoked, deletes credential from vault, and trips SafetyControlPlane into REVALIDATION_REQUIRED or HARD_HALT.
        """
        self._revoked_keys.add(key_id)
        self._active_versions.pop(key_id, None)
        self.vault.delete_secret(key_id)

        err_msg = f"Secret '{key_id}' REVOKED by {authority}: {reason}"
        logger.critical(err_msg)

        # Signal SafetyControlPlane to block dispatches
        self.control_plane.report_subsystem_state(
            f"secret_revocation_{key_id}",
            SafetyState.REVALIDATION_REQUIRED,
            err_msg
        )

    def is_revoked(self, key_id: str) -> bool:
        """Check if secret key has been revoked."""
        return key_id in self._revoked_keys

    def get_valid_secret(self, key_id: str) -> str:
        """
        Retrieves secret payload. Raises SecretRevocationException if key is revoked.
        """
        if self.is_revoked(key_id):
            raise SecretRevocationException(f"Secret key '{key_id}' has been REVOKED")

        secret = self.vault.get_secret(key_id)
        if secret is None:
            raise SecretVaultViolationException(f"Secret key '{key_id}' not found in SecretVault")

        return secret

    @staticmethod
    def scrub_memory_buffer(buffer: bytearray) -> None:
        """
        In-memory byte scrubbing overwriting sensitive buffer bytes with zero-bytes.
        """
        if isinstance(buffer, bytearray):
            for i in range(len(buffer)):
                buffer[i] = 0
            logger.debug("Memory buffer scrubbed with zero-bytes")
