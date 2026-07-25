# contracts/shadow_contracts.py
"""
Canonical Shadow Mode Contracts & Domain Models for NexTrade (Sub-Phase 4G).
Defines strongly typed, frozen dataclasses for non-executing shadow comparison records,
simulated execution status, and statistical comparison reports for 4H promotion gating.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class ShadowOrderStatus(str, Enum):
    SHADOW_SUBMITTED = "SHADOW_SUBMITTED"
    SHADOW_FILLED = "SHADOW_FILLED"
    SHADOW_PARTIALLY_FILLED = "SHADOW_PARTIALLY_FILLED"
    SHADOW_MISSED = "SHADOW_MISSED"
    SHADOW_REJECTED = "SHADOW_REJECTED"


@dataclass(frozen=True)
class ShadowExecutionRecord:
    """
    Immutable comparison record capturing simulated execution outcome vs real market ticks.
    """
    shadow_id: str
    execution_request_id: str
    symbol: str
    side: str
    quantity: float
    limit_price: float
    simulated_fill_price: float
    market_tick_price: float
    slippage_bps: float
    timing_delta_ms: float
    status: ShadowOrderStatus
    safety_gate_denial_reasons: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ShadowComparisonReport:
    """
    Statistical evaluation report comparing shadow performance against live market conditions.
    """
    report_id: str
    total_shadow_orders: int
    simulated_fill_count: int
    missed_fill_count: int
    simulated_fill_rate: float
    average_slippage_bps: float
    max_slippage_bps: float
    average_timing_delta_ms: float
    safety_gate_denials_count: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
