"""NexTrade Quant Research Lab package (Phase 7A scaffold)."""

from research.backtest_protocol import (
    BacktestConstraints,
    BacktestCostModel,
    BacktestEngine,
    BacktestResult,
    NullBacktestEngine,
)
from research.certification_store import CertificationStore
from research.legacy_backtest_adapter import LegacyBacktestAdapter
from research.robustness import MonteCarloEngine, WalkForwardEngine, build_walk_forward_windows
from research.strategy_certification_engine import StrategyCertificationEngine

__all__ = [
    "BacktestConstraints",
    "BacktestCostModel",
    "BacktestEngine",
    "BacktestResult",
    "NullBacktestEngine",
    "LegacyBacktestAdapter",
    "WalkForwardEngine",
    "MonteCarloEngine",
    "build_walk_forward_windows",
    "CertificationStore",
    "StrategyCertificationEngine",
]
