"""
NexTrade Phase 5F — Broker Rule Registry Manager.

Manages broker-isolated rule packages with durable version lineage, rollback protection,
and cross-broker rule isolation.
"""

import threading
import logging
from typing import Dict, Any, Optional, Tuple

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from .signed_rule_validator import SignedRulePackage, SignedRulePackageValidator, InvalidSignatureException, HashMismatchException

logger = logging.getLogger("BrokerRuleRegistryManager")


class RollbackAttemptException(Exception):
    """Raised when an attempt is made to activate a rule package with a lower version number."""
    pass


class SecurityBreachException(Exception):
    """Raised when a security integrity failure is detected (tampering, same version hash mismatch, etc.)."""
    pass


class BrokerIsolationException(Exception):
    """Raised when a rule package is submitted for an unintended broker."""
    pass


class BrokerRuleRegistryManager:
    """
    Registry maintaining broker-isolated active rule packages and durable version lineage.
    """

    def __init__(
        self,
        validator: Optional[SignedRulePackageValidator] = None,
        control_plane: Optional[SafetyControlPlane] = None
    ) -> None:
        self.validator = validator or SignedRulePackageValidator()
        self.control_plane = control_plane or SafetyControlPlane()
        self._lock = threading.RLock()
        
        # In-memory storage: broker_id -> SignedRulePackage
        self._active_packages: Dict[str, SignedRulePackage] = {}
        
        # Durable version lineage: (broker_id, rule_family) -> (highest_version, package_hash)
        self._lineage_records: Dict[Tuple[str, str], Tuple[int, str]] = {}

    def register_rule_package(self, broker_id: str, package: SignedRulePackage) -> None:
        """
        Validates, lineage-checks, and registers a signed rule package for a specific broker.
        """
        with self._lock:
            # 1. Broker Isolation Check
            if package.broker_id != broker_id:
                err = f"Cross-broker isolation violation! Package broker_id '{package.broker_id}' mismatch with target '{broker_id}'"
                logger.critical(err)
                self.control_plane.report_subsystem_state("rule_registry", SafetyState.HARD_HALT, err)
                raise BrokerIsolationException(err)

            # 2. Cryptographic Authenticity Verification
            try:
                self.validator.validate_package(package)
            except (InvalidSignatureException, HashMismatchException) as e:
                err = f"SECURITY BREACH in rule package: {str(e)}"
                logger.critical(err)
                self.control_plane.report_subsystem_state("rule_registry", SafetyState.HARD_HALT, err)
                raise SecurityBreachException(err)

            # 3. Durable Lineage & Rollback Protection
            lineage_key = (broker_id, package.rule_family)
            if lineage_key in self._lineage_records:
                highest_ver, highest_hash = self._lineage_records[lineage_key]

                # Rollback attempt (lower version)
                if package.version < highest_ver:
                    err = f"Rollback attempt rejected: Package v{package.version} < active v{highest_ver} for broker '{broker_id}'"
                    logger.warning(err)
                    raise RollbackAttemptException(err)

                # Same version, different hash (tampering/collision)
                if package.version == highest_ver and package.package_hash != highest_hash:
                    err = f"SECURITY BREACH: Replayed version v{package.version} with hash mismatch ({package.package_hash} != {highest_hash})"
                    logger.critical(err)
                    self.control_plane.report_subsystem_state("rule_registry", SafetyState.HARD_HALT, err)
                    raise SecurityBreachException(err)

            # Store package and update lineage
            self._active_packages[broker_id] = package
            self._lineage_records[lineage_key] = (package.version, package.package_hash)
            logger.info("Broker '%s' registered rule package '%s' v%d successfully.", broker_id, package.package_id, package.version)

    def get_active_rule_package(self, broker_id: str) -> Optional[SignedRulePackage]:
        """
        Retrieves active rule package for broker.
        Fail-closed: if missing, trips SafetyControlPlane to REVALIDATION_REQUIRED and returns None.
        """
        with self._lock:
            if broker_id not in self._active_packages:
                err = f"No active rule package for broker '{broker_id}'. Fail-closed enforcement."
                logger.warning(err)
                self.control_plane.report_subsystem_state("rule_registry", SafetyState.REVALIDATION_REQUIRED, err)
                return None
            return self._active_packages[broker_id]
