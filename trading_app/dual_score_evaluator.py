"""
NexTrade Phase 7P — Dual Score Evaluation Engine.

Provides separate measurement between System Intelligence Quality Score (0-100)
and Trading Performance Score (0-100) to distinguish decision-making quality from market luck.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Any

logger = logging.getLogger("DualScoreEvaluator")


@dataclass
class DualScoreMetrics:
    intelligence_quality_score: float  # 0 - 100 (Decision-making Quality)
    trading_performance_score: float   # 0 - 100 (Financial & Execution Quality)
    regime_accuracy_pct: float
    counterfactual_advantage_pct: float
    data_quality_pass_rate_pct: float
    profit_factor: float
    win_rate_pct: float
    max_drawdown_pct: float
    evaluation_summary: str


class DualScoreEvaluator:
    """Evaluates separate Intelligence Quality and Trading Performance scores."""

    def calculate_dual_scores(
        self,
        regime_accuracy_pct: float,
        counterfactual_advantage_pct: float,
        data_quality_pass_rate_pct: float,
        profit_factor: float,
        win_rate_pct: float,
        max_drawdown_pct: float
    ) -> DualScoreMetrics:
        """Calculates Dual Scores (0 - 100)."""

        # 1. Intelligence Quality Score (Data Quality 30%, Regime Accuracy 40%, Counterfactual Advantage 30%)
        intel_score = (
            (min(100.0, data_quality_pass_rate_pct) * 0.30) +
            (min(100.0, regime_accuracy_pct) * 0.40) +
            (min(100.0, max(0.0, counterfactual_advantage_pct)) * 0.30)
        )
        intel_score = round(max(0.0, min(100.0, intel_score)), 1)

        # 2. Trading Performance Score (Profit Factor 40%, Win Rate 30%, Drawdown Protection 30%)
        pf_score = min(100.0, (profit_factor / 2.0) * 100.0)
        dd_score = max(0.0, 100.0 - (max_drawdown_pct * 5.0))
        
        perf_score = (
            (pf_score * 0.40) +
            (min(100.0, win_rate_pct) * 0.30) +
            (dd_score * 0.30)
        )
        perf_score = round(max(0.0, min(100.0, perf_score)), 1)

        summary = (
            f"Intelligence Quality: {intel_score}/100 | "
            f"Trading Performance: {perf_score}/100 | "
            f"PF: {profit_factor:.2f} | Win Rate: {win_rate_pct:.1f}%"
        )

        return DualScoreMetrics(
            intelligence_quality_score=intel_score,
            trading_performance_score=perf_score,
            regime_accuracy_pct=regime_accuracy_pct,
            counterfactual_advantage_pct=counterfactual_advantage_pct,
            data_quality_pass_rate_pct=data_quality_pass_rate_pct,
            profit_factor=profit_factor,
            win_rate_pct=win_rate_pct,
            max_drawdown_pct=max_drawdown_pct,
            evaluation_summary=summary
        )
