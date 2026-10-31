"""
OIE-001 — Central Angel REST rate limiter with cooldown on rate-limit / reset.

All Angel REST calls from the web dashboard / bridge should go through
`angel_rest_call` so UI polling cannot storm the broker API.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("AngelRestLimiter")

T = TypeVar("T")

_lock = threading.Lock()
_min_interval_sec = 0.35  # ~2.8 req/s hard ceiling across process
_last_call_ts = 0.0
_cooldown_until = 0.0
_cooldown_reason: Optional[str] = None


def rest_in_cooldown() -> bool:
    return time.time() < float(_cooldown_until)


def rest_cooldown_remaining() -> float:
    return max(0.0, float(_cooldown_until) - time.time())


def trip_rest_cooldown(seconds: float = 30.0, reason: str = "rate_limit") -> None:
    global _cooldown_until, _cooldown_reason
    with _lock:
        _cooldown_until = max(float(_cooldown_until), time.time() + float(seconds))
        _cooldown_reason = reason
    logger.warning("Angel REST cooldown %.0fs — %s", seconds, reason)


def _looks_rate_limited(exc_or_msg: Any) -> bool:
    text = str(exc_or_msg or "").lower()
    return any(
        k in text
        for k in (
            "access rate",
            "rate limit",
            "too many",
            "exceeding access",
            "10054",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
        )
    )


def _looks_invalid_api_key(exc_or_msg: Any) -> bool:
    text = str(exc_or_msg or "").lower()
    return "invalid api key" in text or "ag8004" in text


def angel_rest_call(label: str, fn: Callable[[], T], *, bypass_cooldown: bool = False) -> T:
    """
    Serialize Angel REST calls with min spacing + cooldown on broker rejection.
    Raises RuntimeError if in cooldown (unless bypass_cooldown).
    """
    global _last_call_ts
    with _lock:
        now = time.time()
        if not bypass_cooldown and now < float(_cooldown_until):
            raise RuntimeError(
                f"Angel REST cooldown ({rest_cooldown_remaining():.0f}s left): {_cooldown_reason}"
            )
        wait = float(_min_interval_sec) - (now - float(_last_call_ts))
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.time()

    try:
        result = fn()
        # SmartAPI often returns AG8004 in the body without raising
        try:
            if isinstance(result, dict):
                blob = f"{result.get('message','')} {result.get('errorCode','')} {result.get('errorcode','')}"
                if _looks_invalid_api_key(blob):
                    trip_rest_cooldown(
                        300.0,
                        "AG8004 Invalid API Key — whitelist public IP on Trading app / verify ANGEL_API_KEY",
                    )
        except Exception:
            pass
        return result
    except Exception as exc:
        if _looks_invalid_api_key(exc):
            trip_rest_cooldown(
                300.0,
                "AG8004 Invalid API Key — whitelist public IP on Trading app / verify ANGEL_API_KEY",
            )
        elif _looks_rate_limited(exc):
            trip_rest_cooldown(45.0 if "rate" in str(exc).lower() or "access" in str(exc).lower() else 20.0, str(exc)[:120])
        raise
