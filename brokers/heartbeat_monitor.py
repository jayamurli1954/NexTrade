"""
NexTrade Phase 5B — Monotonic Clock Integrity & Multi-Channel Heartbeat Monitor.

Uses time.monotonic() to track ORDER_CHANNEL and MARKET_DATA_CHANNEL health,
detecting heartbeat drops, market data staleness, and latency breaches.
"""

import time
import logging
from typing import Dict, Any, Optional

from .connectivity_policy import BrokerConnectivityPolicy
from .connection_state_machine import BrokerConnectionStateMachine, ConnectionState, ConnectionFault

logger = logging.getLogger("BrokerHeartbeatMonitor")


class LatencyHardLimitExceededException(Exception):
    """Raised when round-trip latency exceeds configured hard limit."""
    pass


class HeartbeatTimeoutException(Exception):
    """Raised when channel heartbeat fails to respond within timeout window."""
    pass


class ClockIntegrityMonitor:
    """
    Monotonic clock integrity monitor protecting against wall-clock skew/NTP jumps.
    """

    @staticmethod
    def now_monotonic() -> float:
        """Returns current monotonic timestamp in seconds."""
        return time.monotonic()

    @staticmethod
    def elapsed_since(start_monotonic: float) -> float:
        """Calculates elapsed seconds using monotonic clock."""
        return max(0.0, time.monotonic() - start_monotonic)


class BrokerHeartbeatMonitor:
    """
    Monitors order socket and market data channel heartbeats and latency.
    """

    def __init__(self, policy: Optional[BrokerConnectivityPolicy] = None, state_machine: Optional[BrokerConnectionStateMachine] = None) -> None:
        self.policy = policy or BrokerConnectivityPolicy(broker_id="DEFAULT", environment="TEST")
        self.state_machine = state_machine
        
        now = ClockIntegrityMonitor.now_monotonic()
        self._last_order_hb_mono = now
        self._last_market_tick_mono = now
        self._last_latency_ms = 10.0
        self._rtt_history = [10.0]

    def record_order_heartbeat(self, latency_ms: float = 10.0) -> float:
        """
        Record order channel heartbeat with measured round-trip latency (RTT).
        """
        self._last_order_hb_mono = ClockIntegrityMonitor.now_monotonic()
        self._last_latency_ms = latency_ms
        self._rtt_history.append(latency_ms)
        if len(self._rtt_history) > 100:
            self._rtt_history.pop(0)

        # Check soft latency warning
        if latency_ms > self.policy.latency_warning_threshold_ms:
            logger.warning("HIGH LATENCY WARNING: Broker RTT is %.1f ms (warning threshold: %.1f ms)",
                           latency_ms, self.policy.latency_warning_threshold_ms)

        # Check latency hard limit
        if latency_ms >= self.policy.latency_hard_limit_ms:
            err_msg = f"LATENCY HARD LIMIT BREACH: RTT is {latency_ms:.1f} ms (hard limit: {self.policy.latency_hard_limit_ms:.1f} ms)"
            logger.critical(err_msg)
            if self.state_machine:
                self.state_machine.record_fault(ConnectionFault.LATENCY_BREACH, err_msg)
            raise LatencyHardLimitExceededException(err_msg)

        return latency_ms

    def record_market_data_tick(self) -> None:
        """Record market data tick timestamp."""
        self._last_market_tick_mono = ClockIntegrityMonitor.now_monotonic()

    def check_health(self) -> Dict[str, Any]:
        """
        Evaluates elapsed monotonic time for order channel heartbeat and market data freshness.
        """
        order_hb_elapsed = ClockIntegrityMonitor.elapsed_since(self._last_order_hb_mono)
        market_tick_elapsed = ClockIntegrityMonitor.elapsed_since(self._last_market_tick_mono)

        status = "HEALTHY"

        # 1. Check Heartbeat Timeout
        if order_hb_elapsed > self.policy.heartbeat_timeout_sec:
            status = "HEARTBEAT_TIMEOUT"
            err_msg = f"Order heartbeat elapsed {order_hb_elapsed:.2f}s exceeds limit {self.policy.heartbeat_timeout_sec:.2f}s"
            logger.error(err_msg)
            if self.state_machine:
                self.state_machine.record_fault(ConnectionFault.HEARTBEAT_TIMEOUT, err_msg)

        # 2. Check Market Data Staleness
        elif market_tick_elapsed > self.policy.market_data_staleness_limit_sec:
            status = "MARKET_DATA_STALE"
            err_msg = f"Market data tick elapsed {market_tick_elapsed:.2f}s exceeds limit {self.policy.market_data_staleness_limit_sec:.2f}s"
            logger.warning(err_msg)
            if self.state_machine:
                self.state_machine.record_fault(ConnectionFault.MARKET_DATA_STALE, err_msg)

        return {
            "status": status,
            "order_heartbeat_elapsed_sec": round(order_hb_elapsed, 3),
            "market_data_elapsed_sec": round(market_tick_elapsed, 3),
            "last_latency_ms": self._last_latency_ms,
            "avg_latency_ms": round(sum(self._rtt_history) / len(self._rtt_history), 2)
        }
