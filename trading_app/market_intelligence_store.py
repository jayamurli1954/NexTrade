"""
NexTrade Phase 7K.2 — Market Intelligence Feature Store & Audit Logger.

Manages historical feature vectors, real-time market data caching, feature importance tracking,
and daily recommendation audit trails across the 1-2 month Paper Trading Sandbox period.
"""

import os
import json
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("MarketIntelligenceStore")

FEATURE_STORE_FILE = "reports/market_feature_store.json"
DAILY_AUDIT_LOG_FILE = "reports/daily_recommendation_audit_log.json"


@dataclass
class MarketFeatureRecord:
    timestamp: str
    nifty_close: float
    bank_nifty_close: float
    vix_level: float
    breadth_ratio: float
    adx_14: float
    rsi_14: float
    atr_14: float
    relative_volume: float
    regime_classified: str
    regime_confidence_pct: float
    top_feature_contributors: List[str]


@dataclass
class DailyRecommendationAuditRecord:
    recommendation_id: str
    date: str
    timestamp: str
    predicted_regime: str
    regime_confidence_pct: float
    recommended_strategy_id: str
    recommended_strategy_name: str
    suitability_score: int
    primary_rationale: List[str]
    alternative_strategies: List[Dict[str, Any]]
    rag_invalidation_rules: List[str]
    mandate_approved: bool
    mandate_id: Optional[str] = None
    actual_eod_pnl: float = 0.0
    actual_regime_match: Optional[str] = None
    recommendation_hit_status: Optional[str] = None # HIT, MISS, NO_TRADE


class MarketIntelligenceStore:
    """Manages feature persistence, ML feature logging, and EOD validation attribution logs."""

    def __init__(self):
        os.makedirs("reports", exist_ok=True)
        self._feature_history: List[MarketFeatureRecord] = self._load_features()
        self._audit_history: List[DailyRecommendationAuditRecord] = self._load_audits()

    def record_feature_vector(self, feature_record: MarketFeatureRecord):
        self._feature_history.append(feature_record)
        self._save_features()
        logger.info("Recorded Feature Vector for %s | Regime: %s", feature_record.timestamp, feature_record.regime_classified)

    def log_daily_recommendation(self, audit_record: DailyRecommendationAuditRecord):
        self._audit_history.append(audit_record)
        self._save_audits()
        logger.info("Logged Daily Recommendation Audit %s for strategy %s", audit_record.recommendation_id, audit_record.recommended_strategy_name)

    def update_eod_attribution(
        self,
        recommendation_id: str,
        actual_eod_pnl: float,
        actual_regime_match: str,
        hit_status: str
    ):
        """Updates EOD attribution for strategy intelligence accuracy measurement."""
        for rec in self._audit_history:
            if rec.recommendation_id == recommendation_id:
                rec.actual_eod_pnl = actual_eod_pnl
                rec.actual_regime_match = actual_regime_match
                rec.recommendation_hit_status = hit_status
                self._save_audits()
                logger.info("Updated EOD Attribution for %s: PnL=₹%.2f, Status=%s", recommendation_id, actual_eod_pnl, hit_status)
                return True
        return False

    def get_audit_history(self) -> List[DailyRecommendationAuditRecord]:
        return self._audit_history

    def _save_features(self):
        try:
            with open(FEATURE_STORE_FILE, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in self._feature_history], f, indent=2)
        except Exception as e:
            logger.error("Failed to save feature store: %s", e)

    def _load_features(self) -> List[MarketFeatureRecord]:
        if os.path.exists(FEATURE_STORE_FILE):
            try:
                with open(FEATURE_STORE_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    return [MarketFeatureRecord(**item) for item in raw]
            except Exception:
                pass
        return []

    def _save_audits(self):
        try:
            with open(DAILY_AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in self._audit_history], f, indent=2)
        except Exception as e:
            logger.error("Failed to save recommendation audits: %s", e)

    def _load_audits(self) -> List[DailyRecommendationAuditRecord]:
        if os.path.exists(DAILY_AUDIT_LOG_FILE):
            try:
                with open(DAILY_AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    return [DailyRecommendationAuditRecord(**item) for item in raw]
            except Exception:
                pass
        return []
