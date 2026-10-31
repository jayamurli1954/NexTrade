"""
NexTrade Backtest Engine Protocol (Awesome Systematic Trading borrow).

Adapters (legacy BacktestEngineV2, future VectorBT, etc.) implement this interface.
No adapter may authorise live orders — research results only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from contracts.strategy_research import BacktestMetricsSummary, StrategyDefinitionDraft


@dataclass(frozen=True)
class BacktestCostModel:
    transaction_cost_bps: float = 5.0
    slippage_bps: float = 5.0
    stamp_duty_bps: float = 0.0


@dataclass(frozen=True)
class BacktestConstraints:
    initial_capital: float = 100_000.0
    max_positions: int = 5
    allow_short: bool = False


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    engine_name: str
    strategy_id: str
    strategy_version: str
    period_start: str
    period_end: str
    metrics: BacktestMetricsSummary
    cost_model: BacktestCostModel
    constraints: BacktestConstraints
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extras: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BacktestEngine(Protocol):
    """Swappable research backtest engine — VectorBT / legacy / event-driven adapters."""

    engine_name: str

    def run(
        self,
        strategy: StrategyDefinitionDraft,
        market_data: Any,
        *,
        costs: Optional[BacktestCostModel] = None,
        constraints: Optional[BacktestConstraints] = None,
    ) -> BacktestResult:
        ...


class NullBacktestEngine:
    """Placeholder engine for contract tests — returns empty metrics."""

    engine_name = "NULL_RESEARCH_ENGINE"

    def run(
        self,
        strategy: StrategyDefinitionDraft,
        market_data: Any,
        *,
        costs: Optional[BacktestCostModel] = None,
        constraints: Optional[BacktestConstraints] = None,
    ) -> BacktestResult:
        costs = costs or BacktestCostModel()
        constraints = constraints or BacktestConstraints()
        return BacktestResult(
            run_id=f"null-{strategy.strategy_id}",
            engine_name=self.engine_name,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            period_start="",
            period_end="",
            metrics=BacktestMetricsSummary(),
            cost_model=costs,
            constraints=constraints,
            notes="Null engine — no market simulation performed",
        )
