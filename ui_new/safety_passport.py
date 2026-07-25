# ui_new/safety_passport.py
"""
Safety Passport & Transparency Generator for NexTrade (Sub-Phase 4M).
Generates two-level user transparency documentation explaining protection boundaries (Level 1)
and 4A–4L certification evidence stack (Level 2) (Invariants 4M-P4, 4M-P8).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List


@dataclass(frozen=True)
class SafetyPassportDocument:
    """
    Two-level transparency document presenting user safety protections and technical evidence stack.
    """
    system_version: str
    level_1_user_protections: List[str]
    level_2_evidence_stack: Dict[str, str]
    disclaimer: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SafetyPassport:
    """
    Generator creating user-facing Safety Passport documents and UI panels.
    """

    def generate_passport(self) -> SafetyPassportDocument:
        """
        Generates full 2-level Safety Passport document.
        """
        now = datetime.now(timezone.utc)
        level_1 = [
            "Excessive Order Quantity & Notional Limits",
            "Cumulative Position Exposure Caps",
            "Max Daily Loss Circuit Breakers",
            "Cryptographic Multi-Certificate Authorization (4H + 4I + 4J)",
            "Finite Authorization Token Expiration",
            "Broker Connectivity & Socket Disconnect Lock",
            "Position Truth Reconciliation Authority",
            "Idempotent Crash Recovery & Recovery Epoch Isolation",
            "Deterministic DLQ Replay & Stale Event Rejection",
            "Disaster Recovery & Database Restore Safeguards",
            "Dominant Emergency Kill Switch (HARD_HALT / REDUCE_ONLY)",
            "Per-Order Human Approval in Stage 1 Pilot"
        ]

        level_2 = {
            "4A Architecture & Invariant Audit": "CERTIFIED (v3.1)",
            "4B Broker Boundary & Neutral Interface": "CERTIFIED (v3.2)",
            "4C Sandbox Verification & Port Security": "CERTIFIED (v3.3)",
            "4D Live Safety Gate & 12 Fail-Closed Barriers": "CERTIFIED (v3.4)",
            "4E Event-Driven Integration & Auditable DLQ": "CERTIFIED (v3.5)",
            "4F Observability, Alerting & 7-Pillar Telemetry": "CERTIFIED (v3.6)",
            "4G Shadow Mode Execution & Slippage Analysis": "CERTIFIED (v3.7)",
            "4H Promotion Validation & Evidence Gate": "CERTIFIED (v3.8)",
            "4I Independent Readiness Audit": "CERTIFIED (v3.9)",
            "4J Controlled Live Staging Gate": "CERTIFIED (v4.0)",
            "4K Controlled Live Pilot Operations": "CERTIFIED (v4.1)",
            "4L Operational Resilience & Incident Certification": "CERTIFIED (v4.2)"
        }

        disclaimer = (
            "IMPORTANT NOTICE: NexTrade's safety systems are engineered to eliminate operational, execution, "
            "and system risks. They cannot eliminate market volatility risk, liquidity gaps, slippage, "
            "or losses arising from adverse price movements. Safety gate authorization does NOT constitute investment advice."
        )

        return SafetyPassportDocument(
            system_version="v4.3-phase-4m-production-readiness-complete",
            level_1_user_protections=level_1,
            level_2_evidence_stack=level_2,
            disclaimer=disclaimer,
            generated_at=now
        )
