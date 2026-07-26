"""
NexTrade Phase 5D — Dynamic Widget Binder.

Subscribes to SafetyControlPlane state change events, dynamically locking or enabling
ui_new trading workspace controls based on real-time canonical SafetyState.
"""

import logging
from typing import Dict, Any, Optional, Callable, List

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from .capability_bridge import CapabilityEnforcerBridge

logger = logging.getLogger("DynamicWidgetBinder")


class DynamicWidgetBinder:
    """
    Subscriber to SafetyControlPlane state changes.
    Evaluates preventative UI disablement (Layer 1 Defence-in-Depth).
    """

    def __init__(self, control_plane: Optional[SafetyControlPlane] = None, capability_bridge: Optional[CapabilityEnforcerBridge] = None) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.capability_bridge = capability_bridge or CapabilityEnforcerBridge()
        
        self._ui_subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._current_control_state: Dict[str, Any] = {}
        
        # Register listener with SafetyControlPlane
        self.control_plane.register_listener(self._on_safety_state_change)
        self._update_control_state(self.control_plane.get_state(), "Initial state evaluation")

    def _on_safety_state_change(self, old_state: SafetyState, new_state: SafetyState, reason: str) -> None:
        """Callback invoked when SafetyControlPlane transitions."""
        logger.info("WidgetBinder notified of SafetyControlPlane change: %s -> %s (%s)", old_state.name, new_state.name, reason)
        self._update_control_state(new_state, reason)

    def _update_control_state(self, current_safety: SafetyState, reason: str) -> None:
        """Recomputes UI control states based on canonical SafetyState."""
        is_permitted = current_safety.is_execution_permitted()
        
        state_text = f"ACTIVE ({current_safety.name})" if is_permitted else f"LOCKED ({current_safety.name}): {reason}"
        
        self._current_control_state = {
            "is_buy_enabled": is_permitted,
            "is_sell_enabled": is_permitted,
            "is_order_entry_allowed": is_permitted,
            "safety_state": current_safety.name,
            "status_text": state_text,
            "is_locked": not is_permitted
        }

        # Notify UI subscribers
        for sub in list(self._ui_subscribers):
            try:
                sub(self._current_control_state)
            except Exception as e:
                logger.error("Error updating UI subscriber: %s", str(e))

    def register_ui_subscriber(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a UI component listener callback."""
        if callback not in self._ui_subscribers:
            self._ui_subscribers.append(callback)
            callback(self._current_control_state)

    def get_ui_control_state(self) -> Dict[str, Any]:
        """Returns snapshot of current UI control states."""
        return dict(self._current_control_state)
