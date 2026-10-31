"""
Robustness research scaffolds (walk-forward + Monte Carlo).

Phase 7B-ready interfaces; implementations are lightweight and research-only.
They do not alter live strategy scoring or risk limits (OIE-001 safe).
"""

from __future__ import annotations

import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from contracts.strategy_research import BacktestMetricsSummary, StrategyDefinitionDraft
from research.backtest_protocol import BacktestCostModel, BacktestEngine, BacktestResult

logger = logging.getLogger("ResearchRobustness")


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass(frozen=True)
class WalkForwardFoldResult:
    window: WalkForwardWindow
    train: Optional[BacktestResult]
    test: BacktestResult


@dataclass(frozen=True)
class WalkForwardReport:
    report_id: str
    strategy_id: str
    strategy_version: str
    folds: List[WalkForwardFoldResult]
    aggregate_test_metrics: BacktestMetricsSummary
    stability_notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class MonteCarloReport:
    report_id: str
    strategy_id: str
    strategy_version: str
    n_simulations: int
    median_total_return_pct: float
    p5_total_return_pct: float
    p95_total_return_pct: float
    median_max_drawdown_pct: float
    ruin_probability_pct: float
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def build_walk_forward_windows(
    start: str,
    end: str,
    *,
    train_days: int = 180,
    test_days: int = 60,
    step_days: int = 60,
) -> List[WalkForwardWindow]:
    """Generate anchored rolling walk-forward windows (calendar days)."""
    s = datetime.strptime(start[:10], "%Y-%m-%d")
    e = datetime.strptime(end[:10], "%Y-%m-%d")
    windows: List[WalkForwardWindow] = []
    cursor = s
    while True:
        train_start = cursor
        train_end = train_start + timedelta(days=train_days)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days)
        if test_end > e:
            break
        windows.append(
            WalkForwardWindow(
                train_start=train_start.strftime("%Y-%m-%d"),
                train_end=train_end.strftime("%Y-%m-%d"),
                test_start=test_start.strftime("%Y-%m-%d"),
                test_end=test_end.strftime("%Y-%m-%d"),
            )
        )
        cursor = cursor + timedelta(days=step_days)
    return windows


def _avg_metrics(results: Sequence[BacktestResult]) -> BacktestMetricsSummary:
    if not results:
        return BacktestMetricsSummary()
    n = len(results)

    def mean(attr: str) -> float:
        return sum(float(getattr(r.metrics, attr) or 0.0) for r in results) / n

    return BacktestMetricsSummary(
        total_trades=int(sum(r.metrics.total_trades for r in results)),
        win_rate_pct=round(mean("win_rate_pct"), 4),
        profit_factor=round(mean("profit_factor"), 4),
        sharpe=round(mean("sharpe"), 4),
        sortino=round(mean("sortino"), 4),
        max_drawdown_pct=round(mean("max_drawdown_pct"), 4),
        total_return_pct=round(mean("total_return_pct"), 4),
        turnover=round(mean("turnover"), 4),
    )


class WalkForwardEngine:
    """Runs an underlying BacktestEngine across walk-forward OOS folds."""

    def __init__(self, engine: BacktestEngine):
        self.engine = engine

    def run(
        self,
        strategy: StrategyDefinitionDraft,
        *,
        symbols: List[str],
        start: str,
        end: str,
        train_days: int = 180,
        test_days: int = 60,
        step_days: int = 60,
        costs: Optional[BacktestCostModel] = None,
        run_train: bool = False,
    ) -> WalkForwardReport:
        windows = build_walk_forward_windows(
            start, end, train_days=train_days, test_days=test_days, step_days=step_days
        )
        folds: List[WalkForwardFoldResult] = []
        for w in windows:
            train_res = None
            if run_train:
                train_res = self.engine.run(
                    strategy,
                    {"symbols": symbols, "start": w.train_start, "end": w.train_end},
                    costs=costs,
                )
            test_res = self.engine.run(
                strategy,
                {"symbols": symbols, "start": w.test_start, "end": w.test_end},
                costs=costs,
            )
            folds.append(WalkForwardFoldResult(window=w, train=train_res, test=test_res))

        agg = _avg_metrics([f.test for f in folds])
        note = (
            f"{len(folds)} OOS folds; train={train_days}d test={test_days}d step={step_days}d. "
            "Research scaffold — parameter re-optimisation per fold not yet enabled."
        )
        return WalkForwardReport(
            report_id=f"wf-{uuid.uuid4().hex[:10]}",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            folds=folds,
            aggregate_test_metrics=agg,
            stability_notes=note,
        )


class MonteCarloEngine:
    """
    Trade-shuffle Monte Carlo on a completed BacktestResult equity path / trade PnLs.

    If trades lack pnl fields, synthesises from equity_curve deltas.
    """

    def run(
        self,
        strategy: StrategyDefinitionDraft,
        base: BacktestResult,
        *,
        n_simulations: int = 500,
        seed: int = 42,
        ruin_drawdown_pct: float = 25.0,
    ) -> MonteCarloReport:
        pnls = self._extract_trade_pnls(base)
        if len(pnls) < 2:
            return MonteCarloReport(
                report_id=f"mc-{uuid.uuid4().hex[:10]}",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.version,
                n_simulations=0,
                median_total_return_pct=0.0,
                p5_total_return_pct=0.0,
                p95_total_return_pct=0.0,
                median_max_drawdown_pct=0.0,
                ruin_probability_pct=0.0,
                notes="Insufficient trade PnLs for Monte Carlo",
            )

        rng = random.Random(seed)
        capital0 = float(base.constraints.initial_capital or 100_000.0)
        finals: List[float] = []
        max_dds: List[float] = []
        ruins = 0

        for _ in range(n_simulations):
            shuffled = pnls[:]
            rng.shuffle(shuffled)
            equity = capital0
            peak = capital0
            max_dd = 0.0
            for p in shuffled:
                equity += p
                peak = max(peak, equity)
                if peak > 0:
                    max_dd = max(max_dd, (peak - equity) / peak * 100.0)
            ret_pct = ((equity - capital0) / capital0) * 100.0 if capital0 else 0.0
            finals.append(ret_pct)
            max_dds.append(max_dd)
            if max_dd >= ruin_drawdown_pct:
                ruins += 1

        finals_sorted = sorted(finals)
        dds_sorted = sorted(max_dds)

        def pctile(xs: List[float], p: float) -> float:
            if not xs:
                return 0.0
            idx = min(len(xs) - 1, max(0, int(math.floor(p * (len(xs) - 1)))))
            return round(xs[idx], 4)

        return MonteCarloReport(
            report_id=f"mc-{uuid.uuid4().hex[:10]}",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.version,
            n_simulations=n_simulations,
            median_total_return_pct=pctile(finals_sorted, 0.5),
            p5_total_return_pct=pctile(finals_sorted, 0.05),
            p95_total_return_pct=pctile(finals_sorted, 0.95),
            median_max_drawdown_pct=pctile(dds_sorted, 0.5),
            ruin_probability_pct=round(100.0 * ruins / max(n_simulations, 1), 4),
            notes=f"Trade-shuffle MC on {len(pnls)} PnL samples; ruin DD≥{ruin_drawdown_pct}%",
        )

    @staticmethod
    def _extract_trade_pnls(base: BacktestResult) -> List[float]:
        pnls: List[float] = []
        for t in base.trades or []:
            if not isinstance(t, dict):
                continue
            for key in ("pnl", "pnl_raw", "profit", "net_pnl"):
                if key in t and t[key] is not None:
                    try:
                        pnls.append(float(t[key]))
                        break
                    except (TypeError, ValueError):
                        continue
        if len(pnls) >= 2:
            return pnls
        curve = base.equity_curve or []
        if len(curve) >= 3:
            return [float(curve[i]) - float(curve[i - 1]) for i in range(1, len(curve))]
        return pnls
