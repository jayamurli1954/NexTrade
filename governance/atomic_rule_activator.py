"""
NexTrade Phase 5E/5F — Atomic Rule Activator & Materiality Manager.

Executes compare-and-swap (CAS) atomic rule activation and classifies updates into
Material (session_epoch++, REVALIDATION_REQUIRED), Security Breach (HARD_HALT), and Non-Material.
"""

import json
import threading
import logging
from typing import Dict, Any, Optional, Set, Tuple

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from .broker_rule_registry import BrokerRuleRegistryManager, SecurityBreachException, RollbackAttemptException
from .signed_rule_validator import SignedRulePackage

logger = logging.getLogger("AtomicRuleActivator")


class StaleActivationAttemptException(Exception):
    """Raised when CAS compare-and-swap activation fails due to expected version mismatch."""
    pass


class AtomicRuleActivator:
    """
    Atomic Rule Activator executing CAS swaps and session_epoch governance.
    """

    MATERIAL_KEYS: Set[str] = {
        "allowed_order_types",
        "allowed_trade_types",
        "margin_multiplier",
        "leverage_cap",
        "lot_size",
        "tick_size",
        "price_bands",
        "product_eligibility"
    }

    def __init__(
        self,
        registry_manager: Optional[BrokerRuleRegistryManager] = None,
        control_plane: Optional[SafetyControlPlane] = None
    ) -> None:
        self.registry_manager = registry_manager or BrokerRuleRegistryManager()
        self.control_plane = control_plane or SafetyControlPlane()
        self._lock = threading.RLock()
        
        # Scoped session_epoch tracker: broker_id -> epoch_integer
        self._session_epochs: Dict[str, int] = {}

    def get_session_epoch(self, broker_id: str) -> int:
        """Retrieves current session_epoch for broker_id."""
        with self._lock:
            return self._session_epochs.get(broker_id, 1)

    def is_material_change(self, old_package: Optional[SignedRulePackage], new_package: SignedRulePackage) -> bool:
        """
        Classifies rule package change as Material or Non-Material.
        Fails closed: any parsing error or unknown key changes are treated as Material.
        """
        if old_package is None:
            return True  # Initial package load is material

        try:
            old_rules = json.loads(old_package.rules_json)
            new_rules = json.loads(new_package.rules_json)

            for key in self.MATERIAL_KEYS:
                if old_rules.get(key) != new_rules.get(key):
                    logger.info("Material change detected in rule key '%s'", key)
                    return True
            return False
        except Exception as e:
            logger.warning("Error evaluating rule materiality (%s). Failing closed as MATERIAL.", str(e))
            return True

    def activate_rule_package_cas(
        self,
        broker_id: str,
        new_package: SignedRulePackage,
        expected_version: Optional[int] = None
    ) -> Tuple[bool, int]:
        """
        Executes CAS Compare-And-Swap atomic activation.
        Returns (is_material, new_session_epoch).
        """
        with self._lock:
            active_pkg = self.registry_manager.get_active_rule_package(broker_id)
            current_ver = active_pkg.version if active_pkg else 0

            # 1. Compare-and-Swap (CAS) Check
            if expected_version is not None and current_ver != expected_version:
                err = f"CAS Activation Failed for broker '{broker_id}': expected v{expected_version}, but current active is v{current_ver}"
                logger.critical(err)
                raise StaleActivationAttemptException(err)

            # 2. Materiality Assessment
            material = self.is_material_change(active_pkg, new_package)

            # 3. Register package (enforces signature, hash, lineage)
            try:
                self.registry_manager.register_rule_package(broker_id, new_package)
            except (SecurityBreachException, RollbackAttemptException) as e:
                logger.critical("Atomic activation aborted for broker '%s': %s", broker_id, str(e))
                raise

            # 4. Process Materiality Impact
            current_epoch = self.get_session_epoch(broker_id)
            if material:
                current_epoch += 1
                self._session_epochs[broker_id] = current_epoch
                reason = f"Material rule package update to v{new_package.version} (Session Epoch {current_epoch})"
                logger.warning("Material rule update! Incrementing session_epoch to %d and tripping REVALIDATION_REQUIRED.", current_epoch)
                self.control_plane.report_subsystem_state("rule_activator", SafetyState.REVALIDATION_REQUIRED, reason)
            else:
                logger.info("Non-material rule update to v%d. CAS atomic swap completed without epoch change.", new_package.version)

            return material, current_epoch
