"""
NexTrade Market Regime & Strategy Recommendation Engine (Hybrid Architecture Wrapper).

Delegates regime detection, feature extraction, strategy suitability scoring, RAG context retrieval,
and LLM explanation generation to the HybridIntelligenceEngine.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from trading_app.strategy_registry import StrategyRegistry, StrategyMetadata, MarketRegimeType
from trading_app.hybrid_intelligence_engine import HybridIntelligenceEngine, HybridIntelligenceOutcome, HybridStrategyScoreCard

logger = logging.getLogger("RegimeRecommendationEngine")


@dataclass
class StrategySuitabilityResult:
    strategy_id: str
    name: str
    suitability_score: int          # 0 - 100
    rank: int
    rationale: str
    rejection_reason: Optional[str] = None


@dataclass
class DailyRecommendationOutcome:
    trade_recommended: bool        # True = Strategy of the Day, False = NO TRADE TODAY
    market_regime: MarketRegimeType
    market_regime_label: str
    nifty_trend: str
    bank_nifty_trend: str
    vix_level: float
    market_breadth: str
    recommended_strategy: Optional[StrategyMetadata]
    suitability_score: int
    primary_rationale: List[str]
    alternative_strategies: List[StrategySuitabilityResult]
    no_trade_reason: Optional[str] = None


class RegimeRecommendationEngine:
    """Wrapper exposing standard recommendation entrypoint backed by HybridIntelligenceEngine."""

    def __init__(self, registry: Optional[StrategyRegistry] = None):
        self.hybrid_engine = HybridIntelligenceEngine(registry=registry)

    def analyze_market_and_recommend(
        self,
        nifty_pct_change: Optional[float] = None,
        bank_nifty_pct_change: Optional[float] = None,
        vix_level: Optional[float] = None,
        advances_count: Optional[int] = None,
        declines_count: Optional[int] = None,
        force_unstable: bool = False
    ) -> DailyRecommendationOutcome:
        """Executes hybrid evaluation; omitted inputs resolve via Angel MarketDataService."""
        outcome = self.hybrid_engine.evaluate_and_recommend(
            nifty_pct_change=nifty_pct_change,
            bank_nifty_pct_change=bank_nifty_pct_change,
            vix_level=vix_level,
            advances_count=advances_count,
            declines_count=declines_count,
            force_unstable=force_unstable
        )

        alts: List[StrategySuitabilityResult] = []
        if outcome.score_cards and len(outcome.score_cards) > 1:
            for sc in outcome.score_cards[1:5]:
                alts.append(StrategySuitabilityResult(
                    strategy_id=sc.strategy_id,
                    name=sc.strategy_name,
                    suitability_score=sc.final_suitability_score,
                    rank=sc.suitability_rank,
                    rationale=sc.rationale
                ))

        nifty_trend = f"POSITIVE (+{outcome.feature_vector.nifty_trend_pct:.2f}%)" if outcome.feature_vector.nifty_trend_pct >= 0 else f"NEGATIVE ({outcome.feature_vector.nifty_trend_pct:.2f}%)"
        bank_nifty_trend = f"POSITIVE (+{outcome.feature_vector.bank_nifty_trend_pct:.2f}%)" if outcome.feature_vector.bank_nifty_trend_pct >= 0 else f"NEGATIVE ({outcome.feature_vector.bank_nifty_trend_pct:.2f}%)"
        breadth_str = f"{advances_count} Advances / {declines_count} Declines"

        return DailyRecommendationOutcome(
            trade_recommended=outcome.trade_recommended,
            market_regime=outcome.market_regime,
            market_regime_label=outcome.market_regime_label,
            nifty_trend=nifty_trend,
            bank_nifty_trend=bank_nifty_trend,
            vix_level=outcome.feature_vector.vix_level,
            market_breadth=breadth_str,
            recommended_strategy=outcome.recommended_strategy,
            suitability_score=outcome.suitability_score,
            primary_rationale=outcome.llm_why_this_strategy,
            alternative_strategies=alts,
            no_trade_reason=outcome.no_trade_reason
        )
