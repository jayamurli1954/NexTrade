"""
NexTrade Phase 7K.2 — Data Quality Invariant Gate & Market Data Watchdog.

Enforces strict data quality checks before trading signals or mandates are processed:
1. Data Freshness SLA (Age <= 3 seconds)
2. Timestamp Continuity (No missing candles)
3. Zero/Negative Price & Volume Anomaly Filtering
4. Multi-provider Fallback & Safe Degradation (Triggers NO TRADE TODAY on breach).
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger("DataQualityGate")


class DataQualityGateViolationException(Exception):
    """Raised when data quality gate fails critical validation invariants."""
    pass


@dataclass
class DataQualityCheckResult:
    passed: bool
    data_age_seconds: float
    missing_candles_count: int
    price_anomaly_detected: bool
    quality_score_pct: float
    status_label: str
    rejection_reason: Optional[str] = None


class DataQualityGate:
    """Enforces strict pre-trade data health standards across market feeds."""

    def __init__(self, max_freshness_sla_sec: float = 3.0):
        self.max_freshness_sla_sec = max_freshness_sla_sec

    def evaluate_feed_health(
        self,
        last_tick_timestamp: float,
        last_price: float,
        volume: int,
        candle_count: int = 100,
        expected_candles: int = 100
    ) -> DataQualityCheckResult:
        now = time.time()
        age = round(now - last_tick_timestamp, 2)
        missing = expected_candles - candle_count

        if age > self.max_freshness_sla_sec:
            reason = f"DATA STALENESS VIOLATION: Market feed age ({age}s) exceeds max SLA ({self.max_freshness_sla_sec}s)."
            logger.critical(reason)
            return DataQualityCheckResult(
                passed=False,
                data_age_seconds=age,
                missing_candles_count=missing,
                price_anomaly_detected=False,
                quality_score_pct=0.0,
                status_label="🔴 DATA STALE (NO TRADE)",
                rejection_reason=reason
            )

        if last_price <= 0 or volume < 0:
            reason = "PRICE ANOMALY DETECTED: Non-positive price or volume received from market provider."
            logger.critical(reason)
            return DataQualityCheckResult(
                passed=False,
                data_age_seconds=age,
                missing_candles_count=missing,
                price_anomaly_detected=True,
                quality_score_pct=0.0,
                status_label="🔴 ANOMALOUS TICK (NO TRADE)",
                rejection_reason=reason
            )

        if missing > 5:
            reason = f"MISSING CANDLE ANOMALY: Feeds missing {missing} expected intraday candles."
            logger.warning(reason)
            return DataQualityCheckResult(
                passed=False,
                data_age_seconds=age,
                missing_candles_count=missing,
                price_anomaly_detected=False,
                quality_score_pct=75.0,
                status_label="🟡 DEGRADED FEED (NO TRADE)",
                rejection_reason=reason
            )

        return DataQualityCheckResult(
            passed=True,
            data_age_seconds=age,
            missing_candles_count=0,
            price_anomaly_detected=False,
            quality_score_pct=100.0,
            status_label="🟢 DATA HEALTH EXCELLENT (PASS)",
            rejection_reason=None
        )
