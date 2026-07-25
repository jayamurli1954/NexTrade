# governance/activation_manager.py
"""
Production Activation & Governance Manager for NexTrade (Sub-Phase 4N).
Enforces Invariant 4N-P2: Production Activation Pending Human Authorization.
Ensures that software readiness certification NEVER automatically enables production execution.
"""
import uuid
import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any


class ProductionActivationManager:
    """
    Thread-safe governance manager requiring explicit operator signature for production activation.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._is_production_active = False
        self._activation_record: Optional[Dict[str, Any]] = None

    @property
    def is_production_active(self) -> bool:
        with self._lock:
            return self._is_production_active

    def authorize_production_activation(
        self,
        operator_id: str,
        human_authorization_id: str,
        readiness_certificate_id: str
    ) -> Tuple[bool, str]:
        """
        Grants production activation ONLY with explicit operator signature (Invariant 4N-P2).
        """
        with self._lock:
            if not operator_id or not human_authorization_id:
                return False, "ACTIVATION_DENIED: Explicit operator_id and human_authorization_id are required"

            if not readiness_certificate_id:
                return False, "ACTIVATION_DENIED: Valid ProductionReadinessCertificate ID is required"

            now = datetime.now(timezone.utc)
            activation_id = f"ACT-PROD-{uuid.uuid4().hex[:12].upper()}"

            self._is_production_active = True
            self._activation_record = {
                "activation_id": activation_id,
                "operator_id": operator_id,
                "human_authorization_id": human_authorization_id,
                "readiness_certificate_id": readiness_certificate_id,
                "activated_at": now.isoformat()
            }

            return True, f"ACTIVATION_SUCCESS: Production activation granted under {activation_id} by operator {operator_id}"

    def revoke_production_activation(self, reason: str = "MANUAL_REVOCATION") -> Tuple[bool, str]:
        """Revokes production activation immediately."""
        with self._lock:
            self._is_production_active = False
            self._activation_record = None
            return True, f"ACTIVATION_REVOKED: Production activation revoked ({reason})"
