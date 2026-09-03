"""
Adapter: existing BacktestEngineV2 → research.BacktestEngine protocol.

Research/display historical path only (yfinance). Never paper-fill authority (OIE-001).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from contracts.strategy_research import BacktestMetricsSummary, StrategyDefinitionDraft
from research.backtest_protocol import (
    BacktestConstraints,
    BacktestCostModel,
    BacktestResult,
)

logger = logging.getLogger("LegacyBacktestAdapter")


class LegacyBacktestAdapter:
    """
    Wraps backtesting.backtest_engine_v2.BacktestEngineV2 behind the Quant Lab protocol.

    market_data expects:
      {"symbols": ["RELIANCE", ...], "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    or a list of symbols (uses draft metadata / defaults for dates).
    """

    engine_name = "NEXTRADE_LEGACY_BACKTEST_V2"

    def __init__(self, initial_capital: float = 100_000.0, position_size_pct: float = 0.02):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct

    def run(
        self,
        strategy: StrategyDefinitionDraft,
        market_data: Any,
        *,
        costs: Optional[BacktestCostModel] = None,
        constraints: Optional[BacktestConstraints] = None,
    ) -> BacktestResult:
        costs = costs or BacktestCostModel()
        constraints = constraints or BacktestConstraints(initial_capital=self.initial_capital)
        symbols, start, end = self._parse_market_data(market_data, strategy)

        from backtesting.backtest_engine_v2 import BacktestEngineV2

        engine = BacktestEngineV2(
            initial_capital=constraints.initial_capital,
            position_size_pct=self.position_size_pct,
        )
        report = engine.run_backtest(symbols, start, end)
        metrics_raw = (report or {}).get("metrics") or getattr(engine, "metrics", {}) or {}

        metrics = BacktestMetricsSummary(
            total_trades=int(metrics_raw.get("total_trades") or 0),
            win_rate_pct=float(metrics_raw.get("win_rate") or 0.0),
            profit_factor=float(metrics_raw.get("profit_factor") or 0.0),
            sharpe=float(metrics_raw.get("sharpe_ratio") or 0.0),
            sortino=float(metrics_raw.get("sortino_ratio") or 0.0),
            max_drawdown_pct=float(metrics_raw.get("max_drawdown_pct") or 0.0),
            total_return_pct=float(metrics_raw.get("total_return_pct") or 0.0),
            turnover=float(metrics_raw.get("turnover") or 0.0),
        )

        trades = list(getattr(engine, "closed_trades", None) or (report or {}).get("trades") or [])
        equity = list(getattr(engine, "daily_capital", None) or [])

        return BacktestResult(
            run_id=f"legacy-{uuid.uuid4().hex[:10]}",
            engine_name=self.engine_name,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            period_start=str(start)[:10],
            period_end=str(end)[:10],
            metrics=metrics,
            cost_model=costs,
            constraints=constraints,
            trades=trades if isinstance(trades, list) else [],
            equity_curve=[float(x) for x in equity] if equity else [],
            notes=(
                f"Legacy V2 adapter for research draft {strategy.strategy_id}@{strategy.version}; "
                f"universe={symbols}. Strategy entry/exit rules in draft are not yet mapped — "
                f"engine uses its built-in signal logic (research scaffolding)."
            ),
            extras={"symbols": symbols, "raw_report_keys": list((report or {}).keys())},
        )

    @staticmethod
    def _parse_market_data(
        market_data: Any,
        strategy: StrategyDefinitionDraft,
    ) -> tuple:
        if isinstance(market_data, dict):
            symbols = market_data.get("symbols") or market_data.get("universe") or ["RELIANCE"]
            start = market_data.get("start") or market_data.get("start_date") or "2024-01-01"
            end = market_data.get("end") or market_data.get("end_date") or datetime.now().strftime("%Y-%m-%d")
        elif isinstance(market_data, (list, tuple)):
            symbols = list(market_data)
            start, end = "2024-01-01", datetime.now().strftime("%Y-%m-%d")
        else:
            symbols = ["RELIANCE"]
            start, end = "2024-01-01", datetime.now().strftime("%Y-%m-%d")
            logger.warning(
                "LegacyBacktestAdapter: market_data missing — defaulting to %s %s→%s",
                symbols,
                start,
                end,
            )
        if isinstance(symbols, str):
            symbols = [symbols]
        symbols = [str(s).upper().replace(".NS", "") for s in symbols if s]
        return symbols, start, end
