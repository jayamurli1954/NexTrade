"""
NexTrade Phase 7K.1 — Market Data Acquisition, Data Quality Gate & Live Feed Engine.

GS Quant borrow P1 / OIE-001:
  All index snapshots resolve through Canonical MarketDataService (Angel authority).
  Hard-coded / simulated index LTP is no longer used as a quality-passing live feed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("MarketDataFeed")


class DataQualityViolationException(Exception):
    """Raised when market data violates freshness SLAs or contains invalid price anomalies."""
    pass


@dataclass
class MarketBreadthSnapshot:
    advances: int
    declines: int
    unchanged: int
    ratio: float
    timestamp: str


@dataclass
class IndexSnapshot:
    symbol: str
    last_price: float
    change_val: float
    change_pct: float
    high: float
    low: float
    open: float
    prev_close: float
    volume: int
    timestamp: str


@dataclass
class MarketSnapshot:
    nifty_50: IndexSnapshot
    bank_nifty: IndexSnapshot
    india_vix: float
    breadth: MarketBreadthSnapshot
    global_bias: str
    is_live: bool
    data_freshness_seconds: float
    data_quality_passed: bool
    error_message: Optional[str] = None
    data_authority: str = ""
    source: str = ""


def _empty_index(symbol: str, now_str: str) -> IndexSnapshot:
    return IndexSnapshot(
        symbol=symbol,
        last_price=0.0,
        change_val=0.0,
        change_pct=0.0,
        high=0.0,
        low=0.0,
        open=0.0,
        prev_close=0.0,
        volume=0,
        timestamp=now_str,
    )


class MarketDataFeedManager:
    """Acquires live market data feeds via MarketDataService; enforces quality gates."""

    def __init__(self, max_freshness_sla_sec: float = 15.0):
        # Align with OIE-001 WS max age (15s); prior 3s SLA was aspirational vs Angel ticks.
        self.max_freshness_sla_sec = max_freshness_sla_sec
        self._cached_snapshot: Optional[MarketSnapshot] = None

    def get_latest_market_snapshot(self, allow_simulated_fallback: bool = False) -> MarketSnapshot:
        """
        Fetches current market snapshot from Angel-backed MarketDataService.

        allow_simulated_fallback is retained for API compatibility but ignored:
        synthetic prices must never pass the quality gate (OIE-001).
        """
        if allow_simulated_fallback:
            logger.warning(
                "allow_simulated_fallback=True ignored — synthetic LTP is forbidden under OIE-001"
            )

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            from trading_app.market_data_service import get_market_data_service

            mds = get_market_data_service()
            idx: Dict[str, Any] = mds.get_index_inputs()
            status = mds.get_status()
            authority = str(status.get("data_authority") or "")
            tick_age = status.get("last_tick_age_sec")
            freshness = float(tick_age) if tick_age is not None else 999.0

            if not idx.get("ok"):
                snap = MarketSnapshot(
                    nifty_50=_empty_index("NIFTY 50", now_str),
                    bank_nifty=_empty_index("BANKNIFTY", now_str),
                    india_vix=0.0,
                    breadth=MarketBreadthSnapshot(0, 0, 0, 0.0, now_str),
                    global_bias="UNAVAILABLE",
                    is_live=False,
                    data_freshness_seconds=freshness,
                    data_quality_passed=False,
                    error_message="Angel index inputs unavailable",
                    data_authority=authority or "NO_VALID_MARKET_DATA",
                    source=str(idx.get("source") or "ANGEL_UNAVAILABLE"),
                )
                self._cached_snapshot = snap
                return snap

            nifty_ltp = float(idx.get("nifty_ltp") or 0)
            bank_ltp = float(idx.get("bank_ltp") or 0)
            nifty_pct = float(idx.get("nifty_pct") or 0)
            bank_pct = float(idx.get("bank_pct") or 0)
            vix = float(idx["vix"]) if idx.get("vix") is not None else 0.0

            nifty_prev = nifty_ltp / (1.0 + nifty_pct / 100.0) if nifty_pct != -100 else nifty_ltp
            bank_prev = bank_ltp / (1.0 + bank_pct / 100.0) if bank_pct != -100 else bank_ltp

            advances = int(idx["advances"]) if idx.get("advances") is not None else 0
            declines = int(idx["declines"]) if idx.get("declines") is not None else 0
            unchanged = 0
            ratio = (advances / declines) if declines > 0 else (float(advances) if advances else 0.0)

            quality_ok = (
                nifty_ltp > 0
                and bank_ltp > 0
                and vix > 0
                and freshness <= self.max_freshness_sla_sec
            )

            snap = MarketSnapshot(
                nifty_50=IndexSnapshot(
                    symbol="NIFTY 50",
                    last_price=nifty_ltp,
                    change_val=round(nifty_ltp - nifty_prev, 2),
                    change_pct=round(nifty_pct, 4),
                    high=nifty_ltp,
                    low=nifty_ltp,
                    open=nifty_prev,
                    prev_close=round(nifty_prev, 2),
                    volume=0,
                    timestamp=now_str,
                ),
                bank_nifty=IndexSnapshot(
                    symbol="BANKNIFTY",
                    last_price=bank_ltp,
                    change_val=round(bank_ltp - bank_prev, 2),
                    change_pct=round(bank_pct, 4),
                    high=bank_ltp,
                    low=bank_ltp,
                    open=bank_prev,
                    prev_close=round(bank_prev, 2),
                    volume=0,
                    timestamp=now_str,
                ),
                india_vix=vix,
                breadth=MarketBreadthSnapshot(
                    advances=advances,
                    declines=declines,
                    unchanged=unchanged,
                    ratio=ratio,
                    timestamp=now_str,
                ),
                global_bias="LIVE_ANGEL" if quality_ok else "DEGRADED",
                is_live=bool(status.get("websocket_streaming")),
                data_freshness_seconds=freshness,
                data_quality_passed=quality_ok,
                error_message=None if quality_ok else (
                    f"Index quality gate failed (freshness={freshness:.1f}s, "
                    f"vix={vix}, authority={authority})"
                ),
                data_authority=authority,
                source=str(idx.get("source") or "ANGEL"),
            )
            self._cached_snapshot = snap
            return snap
        except Exception as exc:
            logger.exception("Market snapshot acquisition failed")
            snap = MarketSnapshot(
                nifty_50=_empty_index("NIFTY 50", now_str),
                bank_nifty=_empty_index("BANKNIFTY", now_str),
                india_vix=0.0,
                breadth=MarketBreadthSnapshot(0, 0, 0, 0.0, now_str),
                global_bias="ERROR",
                is_live=False,
                data_freshness_seconds=999.0,
                data_quality_passed=False,
                error_message=str(exc),
                data_authority="NO_VALID_MARKET_DATA",
                source="ERROR",
            )
            self._cached_snapshot = snap
            return snap

    def validate_data_quality(self, snapshot: MarketSnapshot) -> bool:
        """Data Quality Gate checking staleness and price anomalies."""
        if snapshot.data_freshness_seconds > self.max_freshness_sla_sec:
            msg = (
                f"DATA QUALITY FAIL: Market data age ({snapshot.data_freshness_seconds}s) "
                f"exceeds max SLA ({self.max_freshness_sla_sec}s)."
            )
            logger.critical(msg)
            raise DataQualityViolationException(msg)

        if snapshot.india_vix <= 0 or snapshot.nifty_50.last_price <= 0:
            msg = "DATA QUALITY FAIL: Anomalous zero or negative index price detected."
            logger.critical(msg)
            raise DataQualityViolationException(msg)

        if not snapshot.data_quality_passed:
            msg = snapshot.error_message or "DATA QUALITY FAIL: snapshot marked not passed."
            logger.critical(msg)
            raise DataQualityViolationException(msg)

        return True
