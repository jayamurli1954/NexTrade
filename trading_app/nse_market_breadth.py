"""
NSE Advance / Decline breadth (DISPLAY / REGIME only — OIE-001).

Source: https://www.nseindia.com/api/allIndices
Prefer NIFTY TOTAL MARKET; fall back to NIFTY 50.
Never use these counts for paper fills or observation P&L.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("NseMarketBreadth")

_NSE_HOME = "https://www.nseindia.com"
_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices"

# Prefer broad market, then liquid benchmark
_INDEX_PRIORITY = (
    "NIFTY TOTAL MARKET",
    "NIFTY 50",
    "NIFTY BANK",
)

_CACHE_TTL_SEC = 45.0
_STALE_MAX_SEC = 600.0
_cache_lock = threading.Lock()
_refresh_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "fetched_at": 0.0,
    "ok": False,
    "advances": None,
    "declines": None,
    "unchanged": None,
    "index_name": None,
    "source": "NSE_ALL_INDICES",
    "error": None,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-market-indices",
}


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _pick_breadth_row(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        return None
    by_name = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("index") or row.get("indexSymbol") or "").strip().upper()
        if name:
            by_name[name] = row
    for want in _INDEX_PRIORITY:
        row = by_name.get(want.upper())
        if not row:
            continue
        adv = _to_int(row.get("advances"))
        dec = _to_int(row.get("declines"))
        if adv is not None and dec is not None and (adv + dec) > 0:
            return {
                "index_name": str(row.get("index") or want),
                "advances": adv,
                "declines": dec,
                "unchanged": _to_int(row.get("unchanged")) or 0,
            }
    return None


def _http_fetch_all_indices() -> Optional[Dict[str, Any]]:
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed — cannot fetch NSE breadth")
        return None
    try:
        session = requests.Session()
        session.headers.update(_HEADERS)
        session.get(_NSE_HOME, timeout=3)
        resp = session.get(_ALL_INDICES_URL, timeout=5)
        if resp.status_code != 200:
            logger.warning("NSE allIndices HTTP %s", resp.status_code)
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("NSE breadth fetch failed: %s", exc)
        return None


def _cache_snapshot(*, age: float) -> Dict[str, Any]:
    return {
        "ok": bool(_cache.get("ok")),
        "advances": _cache.get("advances"),
        "declines": _cache.get("declines"),
        "unchanged": _cache.get("unchanged"),
        "index_name": _cache.get("index_name"),
        "source": _cache.get("source") or "NSE_ALL_INDICES",
        "error": _cache.get("error"),
        "fetched_at": _cache.get("fetched_at"),
        "cache_age_sec": round(age, 1),
        "breadth_live": bool(_cache.get("ok")),
        "purpose": "DISPLAY_REGIME",
    }


def fetch_nse_advance_decline(*, force: bool = False) -> Dict[str, Any]:
    """
    Live NSE advance/decline counts for regime cockpit.

    Stale-while-singleflight so concurrent /api/mandate polls do not pile up.
    """
    now = time.time()
    with _cache_lock:
        age = now - float(_cache.get("fetched_at") or 0)
        if not force and age < _CACHE_TTL_SEC and _cache.get("ok"):
            return _cache_snapshot(age=age)
        stale = None
        if _cache.get("ok") and age < _STALE_MAX_SEC:
            stale = _cache_snapshot(age=age)

    acquired = _refresh_lock.acquire(blocking=False)
    if not acquired:
        if stale is not None:
            stale["error"] = stale.get("error") or "refresh_in_progress"
            return stale
        return {
            "ok": False,
            "advances": None,
            "declines": None,
            "unchanged": None,
            "index_name": None,
            "source": "NSE_ALL_INDICES",
            "error": "refresh_in_progress",
            "fetched_at": 0.0,
            "cache_age_sec": None,
            "breadth_live": False,
            "purpose": "DISPLAY_REGIME",
        }

    try:
        with _cache_lock:
            age = time.time() - float(_cache.get("fetched_at") or 0)
            if not force and age < _CACHE_TTL_SEC and _cache.get("ok"):
                return _cache_snapshot(age=age)

        payload = _http_fetch_all_indices()
        picked = _pick_breadth_row(payload or {})
        err = None
        if not picked:
            err = "NSE advance/decline unavailable (cookie/network/pre-open)"

        with _cache_lock:
            if picked:
                _cache["fetched_at"] = time.time()
                _cache["ok"] = True
                _cache["advances"] = picked["advances"]
                _cache["declines"] = picked["declines"]
                _cache["unchanged"] = picked["unchanged"]
                _cache["index_name"] = picked["index_name"]
                _cache["error"] = None
            else:
                _cache["error"] = err
            age = time.time() - float(_cache.get("fetched_at") or 0)
            snap = _cache_snapshot(age=age)
            if not snap["ok"] and stale is not None:
                return stale
            return snap
    finally:
        _refresh_lock.release()
