"""
ARASS v1.0 — AI Regime Adaptive Short Straddle (research only).

Does not authorise paper/live orders. Never promotes to Strategy Registry.
Requires explicit certification before any non-research use (OIE-001).
"""

from research.arass.definition import ARASS_PARAMS, build_arass_hypothesis, build_arass_strategy_draft
from research.arass.engine import ArassBacktestEngine

__all__ = [
    "ARASS_PARAMS",
    "ArassBacktestEngine",
    "build_arass_hypothesis",
    "build_arass_strategy_draft",
]
