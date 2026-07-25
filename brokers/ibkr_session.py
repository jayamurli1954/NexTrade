# brokers/ibkr_session.py
"""
IBKR Session & Connection Health Manager for NexTrade (Sub-Phase 4C).
Monitors IBKR paper socket session health, connection state transitions,
heartbeats, and automated reconnection with exponential backoff.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
import time

from config.ibkr_config import IBKRConfig, validate_sandbox_config


class IBKRSessionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"


@dataclass
class IBKRSessionManager:
    """Manages session lifecycle and health monitoring for IBKR adapter."""
    config: IBKRConfig = field(default_factory=IBKRConfig)
    state: IBKRSessionState = IBKRSessionState.DISCONNECTED
    last_heartbeat: Optional[datetime] = None
    failed_reconnect_attempts: int = 0
    total_reconnections: int = 0

    def __post_init__(self):
        validate_sandbox_config(self.config, live_trading_enabled=False)

    def mark_connected(self) -> None:
        """Mark session as active and connected."""
        self.state = IBKRSessionState.CONNECTED
        self.last_heartbeat = datetime.now(timezone.utc)
        self.failed_reconnect_attempts = 0

    def mark_disconnected(self, reason: str = "") -> None:
        """Mark session as disconnected."""
        self.state = IBKRSessionState.DISCONNECTED

    def record_heartbeat(self) -> None:
        """Record heartbeat tick from IBKR socket."""
        self.last_heartbeat = datetime.now(timezone.utc)
        if self.state == IBKRSessionState.DEGRADED:
            self.state = IBKRSessionState.CONNECTED

    def attempt_reconnect(self, transport_connect_fn) -> bool:
        """
        Attempts session reconnection using configured exponential backoff.
        Returns True if reconnection succeeds.
        """
        validate_sandbox_config(self.config, live_trading_enabled=False)
        self.state = IBKRSessionState.RECONNECTING

        while self.failed_reconnect_attempts < self.config.max_reconnect_attempts:
            self.failed_reconnect_attempts += 1
            success = transport_connect_fn()
            if success:
                self.mark_connected()
                self.total_reconnections += 1
                return True
            time.sleep(self.config.reconnect_backoff_seconds * self.failed_reconnect_attempts)

        self.state = IBKRSessionState.DISCONNECTED
        return False

    def health_report(self) -> Dict[str, Any]:
        """Return comprehensive session health status dictionary."""
        return {
            "session_state": self.state.value,
            "is_connected": self.state == IBKRSessionState.CONNECTED,
            "port": self.config.port,
            "is_paper_account": self.config.is_paper_account,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "failed_reconnect_attempts": self.failed_reconnect_attempts,
            "total_reconnections": self.total_reconnections
        }
