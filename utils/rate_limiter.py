# utils/rate_limiter.py
"""
Thread-Safe Atomic Sliding-Window Rate Limiter for NexTrade (Sub-Phase 4D).
Combines token availability checking and reservation into a single atomic operation
to prevent race conditions under concurrent order submission environments.
"""
from datetime import datetime, timezone
import threading
from typing import List


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding-window rate limiter enforcing maximum operations per time window.
    """

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        if max_requests <= 0:
            raise ValueError("max_requests must be a positive integer")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: List[float] = []
        self._lock = threading.RLock()

    def try_acquire(self, now_timestamp: float = None) -> bool:
        """
        Atomically checks availability and acquires 1 token if within rate limit.
        Returns True if acquired; False if rate limit breached.
        """
        with self._lock:
            now = now_timestamp if now_timestamp is not None else datetime.now(timezone.utc).timestamp()
            cutoff = now - self.window_seconds

            # Prune timestamps older than window_seconds
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]

            if len(self._timestamps) < self.max_requests:
                self._timestamps.append(now)
                return True
            else:
                return False

    def reset() -> None:
        """Reset all rate limiter token history."""
        with self._lock:
            self._timestamps.clear()

    @property
    def current_count(self) -> int:
        """Return number of tokens currently consumed in sliding window."""
        with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            cutoff = now - self.window_seconds
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]
            return len(self._timestamps)
