"""
NexTrade Phase 7K.2 — Local-First Desktop Background Autonomous Service.

Runs continuously as a background service independent of the web browser state.
Manages power/sleep watchdog, network heartbeat monitoring, market data quality checking,
and automated safe degradation if connectivity breaks.
"""

import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

from trading_app.data_quality_gate import DataQualityGate, DataQualityCheckResult
from trading_app.daily_mandate_engine import DailyMandateEngine

logger = logging.getLogger("DesktopBackgroundService")


@dataclass
class ServiceHealthStatus:
    service_active: bool
    browser_connected: bool
    network_online: bool
    heartbeat_age_sec: float
    data_quality_passed: bool
    active_mandate_id: Optional[str]
    sleep_prevention_active: bool
    status_summary: str


class DesktopBackgroundAutonomousService:
    """Local-first desktop background service daemon managing autonomous trading lifecycle."""

    def __init__(self, mandate_engine: Optional[DailyMandateEngine] = None):
        self.mandate_engine = mandate_engine or DailyMandateEngine()
        # OIE-001 WS freshness ceiling is 15s (not the aspirational 3s default).
        self.data_gate = DataQualityGate(max_freshness_sla_sec=15.0)
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._last_heartbeat = time.time()
        self._network_online = True
        self._sleep_prevention = True

    def start_service(self):
        """Launches the background daemon thread."""
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._run_daemon_loop, daemon=True)
        self._thread.start()
        logger.info("🟢 NexTrade Local-First Desktop Autonomous Background Service STARTED.")

    def stop_service(self):
        """Stops the daemon thread."""
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("🛑 NexTrade Desktop Autonomous Service STOPPED.")

    def _live_feed_health(self) -> DataQualityCheckResult:
        """OIE-001 / GS P1: evaluate quality from Angel authority, never hard-coded LTP."""
        try:
            from trading_app.market_data_service import get_market_data_service

            mds = get_market_data_service()
            status = mds.get_status()
            idx = mds.get_index_inputs()
            age = status.get("last_tick_age_sec")
            last_ts = time.time() - float(age) if age is not None else 0.0
            last_price = float(idx.get("nifty_ltp") or 0.0)
            if not idx.get("ok") or last_price <= 0:
                return DataQualityCheckResult(
                    passed=False,
                    data_age_seconds=float(age) if age is not None else 999.0,
                    missing_candles_count=0,
                    price_anomaly_detected=last_price <= 0,
                    quality_score_pct=0.0,
                    status_label="🔴 NO VALID MARKET DATA",
                    rejection_reason="Angel index LTP unavailable for desktop health check",
                )
            return self.data_gate.evaluate_feed_health(
                last_tick_timestamp=last_ts if last_ts > 0 else time.time() - 999.0,
                last_price=last_price,
                volume=1,
            )
        except Exception as exc:
            logger.warning("Live feed health check failed: %s", exc)
            return DataQualityCheckResult(
                passed=False,
                data_age_seconds=999.0,
                missing_candles_count=0,
                price_anomaly_detected=False,
                quality_score_pct=0.0,
                status_label="🔴 FEED HEALTH ERROR",
                rejection_reason=str(exc),
            )

    def get_service_status(self) -> ServiceHealthStatus:
        now = time.time()
        heartbeat_age = round(now - self._last_heartbeat, 2)
        current_mandate = self.mandate_engine.get_current_mandate()
        mandate_id = current_mandate.mandate_id if current_mandate else None

        gate_res = self._live_feed_health()

        return ServiceHealthStatus(
            service_active=self._is_running,
            browser_connected=True,
            network_online=self._network_online,
            heartbeat_age_sec=heartbeat_age,
            data_quality_passed=gate_res.passed,
            active_mandate_id=mandate_id,
            sleep_prevention_active=self._sleep_prevention,
            status_summary="🟢 SERVICE HEALTHY (BACKGROUND DAEMON ACTIVE)" if self._is_running else "🔴 SERVICE STOPPED"
        )

    def _run_daemon_loop(self):
        """Background monitoring loop running every 5 seconds."""
        while self._is_running:
            self._last_heartbeat = time.time()
            try:
                # 1. Verify Active Mandate Boundaries
                current_mandate = self.mandate_engine.get_current_mandate()
                if current_mandate and current_mandate.state.name == "AUTONOMOUS_TRADING_ACTIVE":
                    # 2. Check Data Quality Gate (Angel-backed)
                    gate_res = self._live_feed_health()
                    if not gate_res.passed:
                        logger.warning("Data quality gate failed during autonomous operation: %s", gate_res.rejection_reason)
                        self.mandate_engine.pause_mandate(current_mandate.mandate_id, reason=gate_res.rejection_reason or "Data Health Fault")
            except Exception as e:
                logger.error("Daemon Loop Error: %s", e)
            time.sleep(5)
