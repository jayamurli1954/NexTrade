"""
NSE cash-equity Top Gainers / Losers (DISPLAY / RESEARCH only — OIE-001).

Angel SmartAPI gainersLosers is derivatives-only. Moneycontrol-style equity movers
come from NSE's live-analysis-variations endpoint.

Never use these prices for paper fills or observation P&L.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("NseMarketMovers")

_NSE_HOME = "https://www.nseindia.com"
_GAINERS_URL = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
_LOSERS_URL = "https://www.nseindia.com/api/live-analysis-variations?index=loosers"

# Prefer liquid/F&O equity buckets first (Moneycontrol-style), then broader NSE.
_CATEGORY_PRIORITY = ("FOSec", "SecGtr20", "NIFTYNEXT50", "NIFTY", "BANKNIFTY", "allSec", "SecLwr20")

_CACHE_TTL_SEC = 45.0
_STALE_MAX_SEC = 600.0
_cache_lock = threading.Lock()
_refresh_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "fetched_at": 0.0,
    "gainers": [],
    "losers": [],
    "category": None,
    "error": None,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/top-gainers-loosers",
}


def _parse_pct(row: Dict[str, Any]) -> float:
    for key in ("net_price", "pChange", "perChange", "percentChange", "change_percent"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                continue
    ltp = float(row.get("ltp") or row.get("lastPrice") or 0)
    prev = float(row.get("prev_price") or row.get("previousClose") or row.get("previous_close") or 0)
    if ltp > 0 and prev > 0:
        return ((ltp - prev) / prev) * 100.0
    return 0.0


def _parse_ltp(row: Dict[str, Any]) -> float:
    for key in ("ltp", "lastPrice", "last_price"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                continue
    return 0.0


def _extract_bucket(payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return "", []
    for cat in _CATEGORY_PRIORITY:
        block = payload.get(cat)
        if not isinstance(block, dict):
            continue
        data = block.get("data")
        if isinstance(data, list) and data:
            return cat, data
    # Fallback: first dict child with a non-empty data list
    for key, block in payload.items():
        if key in ("timestamp", "legends") or not isinstance(block, dict):
            continue
        data = block.get("data")
        if isinstance(data, list) and data:
            return str(key), data
    return "", []


def _normalize_rows(raw_rows: List[Dict[str, Any]], *, want_positive: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or row.get("symbolToken") or "").upper().strip()
        if not sym:
            continue
        ltp = _parse_ltp(row)
        chg = _parse_pct(row)
        if ltp <= 0:
            continue
        if want_positive and chg <= 0:
            continue
        if (not want_positive) and chg >= 0:
            continue
        out.append({
            "symbol": sym,
            "ltp": ltp,
            "change_pct": round(chg, 4),
            "source": "NSE_LIVE_ANALYSIS",
            "has_prev_close": True,
            "purpose": "DISPLAY",
        })
    out.sort(key=lambda r: r["change_pct"], reverse=want_positive)
    return out


def _http_fetch(url: str) -> Optional[Dict[str, Any]]:
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed — cannot fetch NSE movers")
        return None
    try:
        session = requests.Session()
        session.headers.update(_HEADERS)
        # Cookie warm-up required by NSE — keep short so /api/status never stalls journal
        session.get(_NSE_HOME, timeout=3)
        resp = session.get(url, timeout=4)
        if resp.status_code != 200:
            logger.warning("NSE movers HTTP %s for %s", resp.status_code, url)
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("NSE movers fetch failed: %s", exc)
        return None


def _cache_snapshot(limit: int, *, age: float) -> Dict[str, Any]:
    return {
        "ok": bool(_cache.get("gainers") or _cache.get("losers")),
        "gainers": list(_cache.get("gainers") or [])[:limit],
        "losers": list(_cache.get("losers") or [])[:limit],
        "category": _cache.get("category"),
        "source": "NSE_LIVE_ANALYSIS",
        "error": _cache.get("error"),
        "fetched_at": _cache.get("fetched_at"),
        "cache_age_sec": round(age, 1),
    }


def fetch_nse_equity_movers(limit: int = 5, *, force: bool = False) -> Dict[str, Any]:
    """
    Market-wide NSE equity top gainers/losers.

    Stale-while-singleflight: concurrent /api/status polls return cached rows
    immediately while one thread refreshes — prevents starving /api/journal.
    """
    now = time.time()
    with _cache_lock:
        age = now - float(_cache.get("fetched_at") or 0)
        has_rows = bool(_cache.get("gainers") or _cache.get("losers"))
        if not force and age < _CACHE_TTL_SEC and has_rows:
            return _cache_snapshot(limit, age=age)
        stale = None
        if has_rows and age < _STALE_MAX_SEC:
            stale = _cache_snapshot(limit, age=age)

    acquired = _refresh_lock.acquire(blocking=False)
    if not acquired:
        if stale is not None:
            stale["error"] = stale.get("error") or "refresh_in_progress"
            return stale
        return {
            "ok": False,
            "gainers": [],
            "losers": [],
            "category": None,
            "source": "NSE_LIVE_ANALYSIS",
            "error": "refresh_in_progress",
            "fetched_at": 0.0,
            "cache_age_sec": None,
        }

    try:
        with _cache_lock:
            age = time.time() - float(_cache.get("fetched_at") or 0)
            has_rows = bool(_cache.get("gainers") or _cache.get("losers"))
            if not force and age < _CACHE_TTL_SEC and has_rows:
                return _cache_snapshot(limit, age=age)

        g_payload = _http_fetch(_GAINERS_URL)
        l_payload = _http_fetch(_LOSERS_URL)
        g_cat, g_raw = _extract_bucket(g_payload or {})
        l_cat, l_raw = _extract_bucket(l_payload or {})
        gainers = _normalize_rows(g_raw, want_positive=True)
        losers = _normalize_rows(l_raw, want_positive=False)
        category = g_cat or l_cat or None
        err = None
        if not gainers and not losers:
            err = "NSE equity movers unavailable (cookie/network/market-closed)"

        with _cache_lock:
            if gainers or losers:
                _cache["fetched_at"] = time.time()
                _cache["gainers"] = gainers
                _cache["losers"] = losers
                _cache["category"] = category
            _cache["error"] = err
            age = time.time() - float(_cache.get("fetched_at") or 0)
            snap = _cache_snapshot(limit, age=age)
            if not snap["ok"] and stale is not None:
                return stale
            return snap
    finally:
        _refresh_lock.release()
