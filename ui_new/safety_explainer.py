# ui_new/safety_explainer.py
"""
Explanatory Rejection & Hold Engine for NexTrade (Sub-Phase 4M).
Translates technical barrier denials, circuit breaker halts, and position reconciliation locks
into human-readable user explanations and required remediation steps (Invariants 4M-P3, 4M-P7).
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class SafetyExplanation:
    """
    Deterministic user-facing explanation object describing order decision outcomes (Invariant 4M-P7).
    """
    decision: str  # READY, HOLD, REJECT
    primary_reason: str
    explanation_text: str
    required_action: str
    active_barriers: List[str] = field(default_factory=list)


class SafetyExplainer:
    """
    Translates internal safety engine results into transparent, actionable user notifications.
    """

    def explain_denial(self, denial_reason: str, context: Optional[Dict[str, Any]] = None) -> SafetyExplanation:
        """
        Generates structured explanation for an order denial or restriction.
        """
        reason_upper = denial_reason.upper()

        if "EXPOSURE" in reason_upper or "NOTIONAL" in reason_upper or "QUANTITY" in reason_upper:
            return SafetyExplanation(
                decision="REJECT",
                primary_reason="Exposure Limit Exceeded",
                explanation_text="The requested order value exceeds the active exposure cap configured for this environment.",
                required_action="Reduce order quantity or close existing positions to release exposure capacity.",
                active_barriers=["S2_NOTIONAL_LIMIT", "S4_EXPOSURE_CAP"]
            )

        if "RECONCILIATION" in reason_upper or "LOCK" in reason_upper:
            return SafetyExplanation(
                decision="HOLD",
                primary_reason="Position Reconciliation Pending",
                explanation_text="Broker-confirmed position truth differs from internal state. New order submissions are held to prevent uncontrolled risk.",
                required_action="Review broker position statement, run reconciliation recovery, and obtain operator acknowledgement.",
                active_barriers=["S7_POSITION_TRUTH", "RECONCILIATION_LOCK"]
            )

        if "DISCONNECT" in reason_upper or "CONNECTION" in reason_upper:
            return SafetyExplanation(
                decision="HOLD",
                primary_reason="Broker Stream Disconnected",
                explanation_text="Real-time broker stream connection is unavailable. Order dispatch is temporarily suspended.",
                required_action="Check network connectivity, wait for automatic stream reconnect, and verify position truth.",
                active_barriers=["S10_BROKER_CONNECTIVITY", "STREAM_LOCK"]
            )

        if "HARD_HALT" in reason_upper or "KILL_SWITCH" in reason_upper:
            return SafetyExplanation(
                decision="REJECT",
                primary_reason="Emergency Kill Switch Active (HARD_HALT)",
                explanation_text="NexTrade is currently under HARD_HALT due to a critical incident or emergency trigger.",
                required_action="Acknowledge active critical alerts and execute manual system recovery procedure.",
                active_barriers=["S12_KILL_SWITCH", "CIRCUIT_BREAKER"]
            )

        return SafetyExplanation(
            decision="REJECT",
            primary_reason="Safety Gate Guardrail Denial",
            explanation_text=f"Order evaluation failed safety check: {denial_reason}",
            required_action="Review order parameters against safety limits and retry.",
            active_barriers=["LIVE_SAFETY_GATE"]
        )
