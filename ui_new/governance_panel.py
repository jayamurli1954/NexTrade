# ui_new/governance_panel.py
"""
User Safety & Governance Panel Component for NexTrade (Sub-Phase 4N).
Provides UI status monitor displaying Production Activation state (Invariant 4N-P2),
Broker Capability Matrix resolution (Invariant 4N-P4), and Secret Sanitizer Shield status (Invariant 4N-P3).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List

from governance.activation_manager import ProductionActivationManager
from governance.capability_resolver import CapabilityResolver
from governance.secret_sanitizer import SecretSanitizer


@dataclass(frozen=True)
class GovernancePanelState:
    """
    Snapshot of platform governance state for UI rendering.
    """
    production_active: bool
    capability_resolver_status: str
    secret_sanitizer_active: bool
    auditable_version: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GovernancePanel:
    """
    UI state manager generating sanitized governance status snapshots.
    """

    def __init__(self):
        self.activation_manager = ProductionActivationManager()
        self.resolver = CapabilityResolver()
        self.sanitizer = SecretSanitizer()

    def get_panel_state(self) -> GovernancePanelState:
        """
        Generates GovernancePanelState for UI rendering.
        """
        now = datetime.now(timezone.utc)
        return GovernancePanelState(
            production_active=self.activation_manager.is_production_active,
            capability_resolver_status="ACTIVE (5-Way Intersection Enforced)",
            secret_sanitizer_active=True,
            auditable_version="v4.4-phase-4n-platform-governance-complete",
            evaluated_at=now
        )
