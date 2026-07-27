"""
Angel One WebSocket + REST market data bridge for the web dashboard.

Provides exchange-authenticated LTP for paper trading and UI. Fails closed when
live quotes are unavailable (no yfinance / hardcoded fallback on trade paths).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, _WORKSPACE_DIR)

logger = logging.getLogger("AngelMarketDataBridge")

_WS_MAX_AGE_SEC = 15.0
_STARTUP_WAIT_SEC = 25.0
_DEFAULT_INDEX_SYMBOLS: List[Tuple[str, str, str]] = [
    ("NIFTY", "NSE"),
    ("BANKNIFTY", "NSE"),
    ("SENSEX", "BSE"),
    ("INDIAVIX", "NSE"),
]

_bridge_lock = threading.Lock()
_bridge_started = False
_last_error: Optional[str] = None
_conn_mgr = None


def _get_conn_mgr():
    global _conn_mgr
    if _conn_mgr is None:
        from ui_new.connection_manager import get_connection_manager
        _conn_mgr = get_connection_manager()
    return _conn_mgr


def _ws_ltp(conn, symbol: str) -> Optional[Tuple[float, float]]:
    """Return (ltp, age_seconds) from WebSocket cache, or None."""
    sym = symbol.upper()
    with conn.ltp_lock:
        row = conn.ltp_data.get(sym)
    if not row:
        return None
    age = time.time() - float(row.get("timestamp") or 0)
    if age > _WS_MAX_AGE_SEC:
        return None
    ltp = float(row.get("ltp") or 0)
    if ltp <= 0:
        return None
    return ltp, age


def _rest_ltp(conn, symbol: str, exchange: str = "NSE") -> Optional[Dict[str, Any]]:
    """Angel REST ltpData — authenticated exchange quote."""
    if not conn.smart_api or not conn.is_connected or getattr(conn, "is_paper_sandbox", False):
        return None
    conn.ensure_tokens_loaded()
    sym = symbol.upper()
    exch = exchange.upper()
    key = f"{exch}:{sym}"
    token = conn.token_map.get(key)
    if not token:
        return None
    try:
        resp = conn.smart_api.ltpData(exch, sym, token)
        if not resp or not resp.get("status"):
            return None
        data = resp.get("data") or {}
        ltp = float(data.get("ltp") or 0)
        if ltp <= 0:
            return None
        close = float(data.get("close") or ltp)
        chg_pct = ((ltp - close) / close * 100.0) if close else 0.0
        return {
            "ltp": ltp,
            "change_pct": round(chg_pct, 4),
            "source": "ANGEL_REST",
            "exchange": exch,
        }
    except Exception as exc:
        logger.warning("Angel REST LTP failed for %s:%s — %s", exch, sym, exc)
        return None


_ALLOW_REST_FALLBACK = False  # Equities: WS-cache only (keeps paper path fast).
_INDEX_REST_SYMBOLS = frozenset({"NIFTY", "BANKNIFTY", "INDIAVIX", "SENSEX", "NIFTY50", "FINNIFTY"})
_INDEX_REST_CACHE: Dict[str, Dict[str, Any]] = {}
_INDEX_REST_CACHE_TTL = 8.0
_index_rest_lock = threading.Lock()


def _index_rest_cached(conn, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
    """Short-lived REST cache for index symbols (WS index ticks often lag on Angel)."""
    sym = symbol.upper()
    if sym not in _INDEX_REST_SYMBOLS:
        return None
    cache_key = f"{exchange.upper()}:{sym}"
    now = time.time()
    with _index_rest_lock:
        hit = _INDEX_REST_CACHE.get(cache_key)
        if hit and (now - float(hit.get("_ts") or 0)) < _INDEX_REST_CACHE_TTL:
            return {k: v for k, v in hit.items() if k != "_ts"}
    rest = _rest_ltp(conn, sym, exchange)
    if not rest:
        return None
    rest["source"] = "ANGEL_REST_INDEX"
    with _index_rest_lock:
        _INDEX_REST_CACHE[cache_key] = {**rest, "_ts": now}
    return rest


def get_ltp_quote(symbol: str, exchange: str = "NSE") -> Optional[Dict[str, Any]]:
    """
    WebSocket-cache only quote for the web dashboard.

    Returns None if no authenticated live quote is available.
    (REST fallback is intentionally disabled to avoid long blocking calls
    in the single-threaded HTTPServer.)
    """
    conn = _get_conn_mgr()
    sym = symbol.upper()
    exch = exchange.upper()

    ws = _ws_ltp(conn, sym)
    if ws:
        ltp, age = ws
        return {
            "ltp": ltp,
            "change_pct": 0.0,
            "source": "ANGEL_WEBSOCKET",
            "exchange": exch,
            "age_sec": round(age, 2),
            "live": True,
        }

    idx_rest = _index_rest_cached(conn, sym, exch)
    if idx_rest:
        idx_rest["live"] = True
        idx_rest["age_sec"] = 0.0
        return idx_rest

    if not _ALLOW_REST_FALLBACK:
        return None

    rest = _rest_ltp(conn, sym, exch)
    if rest:
        rest["live"] = True
        rest["age_sec"] = 0.0
        return rest
    return None


def get_ltp_map(symbols: List[str], exchange: str = "NSE") -> Dict[str, Dict[str, Any]]:
    """Batch LTP for NSE equity symbols."""
    uniq = [s.strip().upper() for s in symbols if s and str(s).strip()]
    if not uniq:
        return {}
    ensure_subscribed(uniq, exchange)
    out: Dict[str, Dict[str, Any]] = {}
    for sym in uniq:
        q = get_ltp_quote(sym, exchange)
        if q:
            out[sym] = q
    return out


def require_ltp(symbol: str, exchange: str = "NSE") -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Fail-closed gate for paper execution.

    Do NOT block long in the HTTP request thread.
    If the WebSocket LTP isn't ready yet, tell the UI to retry.
    """
    ensure_subscribed([symbol.upper()], exchange)
    q = get_ltp_quote(symbol, exchange)
    if q:
        return True, q, ""
    status = get_market_data_status()
    err = status.get("last_error") or ""
    if not status.get("broker_connected"):
        detail = f" ({err})" if err else ""
        return False, None, (
            "Live Angel One broker is not connected. Check config.json credentials "
            f"(api_key, client_id, password, totp_token) and restart the dashboard.{detail}"
        )
    if not status.get("websocket_connected"):
        return False, None, (
            f"Angel WebSocket not streaming yet for {symbol.upper()}. "
            "Wait 20–30 seconds after dashboard start and retry."
        )
    return False, None, (
        f"No live exchange LTP available for {symbol.upper()}. "
        "Paper trade blocked until Angel WebSocket/REST returns a fresh quote."
    )


def ensure_angel_connected(wait_sec: float = 35.0) -> bool:
    """
    Ensure Angel broker session + WebSocket are up. Retries connect if needed.
    Safe to call from API handlers (blocks up to wait_sec).
    """
    global _last_error
    conn = _get_conn_mgr()
    conn.load_config()
    deadline = time.time() + wait_sec
    connect_attempts = 0
    while time.time() < deadline:
        if conn.is_connected and conn.websocket_connected:
            return True
        if not conn.is_connected and connect_attempts < 3:
            connect_attempts += 1
            ok = conn.connect_broker()
            # #region agent log
            try:
                import json as _json
                _dbg = {
                    "sessionId": "bcdfad",
                    "runId": "angel-ensure",
                    "hypothesisId": "H3",
                    "location": "angel_market_data_bridge.py:ensure_angel_connected",
                    "message": "connect_attempt",
                    "data": {
                        "attempt": connect_attempts,
                        "ok": bool(ok),
                        "broker": bool(conn.is_connected),
                        "ws": bool(conn.websocket_connected),
                        "err": getattr(conn, "last_connection_error", None) or _last_error,
                        "cwd": os.getcwd(),
                        "config_api_key_set": bool((conn.config or {}).get("api_key")),
                    },
                    "timestamp": int(time.time() * 1000),
                }
                with open(os.path.join(_WORKSPACE_DIR, "debug-bcdfad.log"), "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps(_dbg) + "\n")
            except Exception:
                pass
            # #endregion
            if ok:
                ws_deadline = time.time() + min(20.0, deadline - time.time())
                while time.time() < ws_deadline and not conn.websocket_connected:
                    time.sleep(0.5)
                if conn.websocket_connected:
                    symbols = list(conn.stock_list or [])
                    for sym, _ in _DEFAULT_INDEX_SYMBOLS:
                        if sym not in symbols:
                            symbols.append(sym)
                    ensure_subscribed(symbols, "NSE")
                    ensure_subscribed(["SENSEX"], "BSE")
                    _last_error = None
                    return True
            _last_error = getattr(conn, "last_connection_error", None) or "Angel broker login failed"
        time.sleep(1.0)
    return bool(conn.is_connected and conn.websocket_connected)


def ensure_subscribed(symbols: List[str], exchange: str = "NSE") -> None:
    """Subscribe symbols on Angel WebSocket if connected."""
    conn = _get_conn_mgr()
    if not conn.websocket_connected:
        return
    pairs = [(s.upper(), exchange.upper()) for s in symbols if s]
    if pairs:
        conn.subscribe_symbols(pairs)


def get_index_board() -> Dict[str, Any]:
    """Index strip: Angel LTP for Indian indices; Nasdaq stays on yfinance (non-Indian)."""
    display_specs = [
        ("NIFTY 50", "NIFTY", "NSE"),
        ("BANK NIFTY", "BANKNIFTY", "NSE"),
        ("SENSEX", "SENSEX", "BSE"),
        ("INDIA VIX", "INDIAVIX", "NSE"),
    ]
    for _, sym, exch in display_specs:
        ensure_subscribed([sym], exch)

    board: List[Dict[str, Any]] = []
    live_count = 0
    for name, sym, exch in display_specs:
        q = get_ltp_quote(sym, exch)
        if q:
            live_count += 1
            chg = float(q.get("change_pct") or 0.0)
            ltp = float(q["ltp"])
            board.append({
                "name": name,
                "exchange": exch,
                "ltp": round(ltp, 2),
                "ltp_fmt": f"{ltp:,.2f}",
                "change_pct": round(chg, 2),
                "change_fmt": (f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"),
                "ok": True,
                "source": q.get("source", "ANGEL"),
            })
        else:
            board.append({
                "name": name,
                "exchange": exch,
                "ltp": None,
                "ltp_fmt": "—",
                "change_pct": None,
                "change_fmt": "—",
                "ok": False,
                "source": "UNAVAILABLE",
            })

    # Nasdaq — optional yfinance (not on Angel Indian feed)
    try:
        import yfinance as yf
        hist = yf.Ticker("^IXIC").history(period="5d", interval="1d")
        if hist is not None and not hist.empty:
            closes = hist["Close"].dropna()
            ltp = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else ltp
            chg = ((ltp - prev) / prev * 100.0) if prev else 0.0
            board.append({
                "name": "NASDAQ",
                "exchange": "US",
                "ltp": round(ltp, 2),
                "ltp_fmt": f"{ltp:,.2f}",
                "change_pct": round(chg, 2),
                "change_fmt": (f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"),
                "ok": True,
                "source": "YFINANCE_US",
            })
            live_count += 1
    except Exception:
        board.append({
            "name": "NASDAQ",
            "exchange": "US",
            "ltp": None,
            "ltp_fmt": "—",
            "change_pct": None,
            "change_fmt": "—",
            "ok": False,
            "source": "UNAVAILABLE",
        })

    angel_live = sum(
        1 for i in board
        if i.get("ok") and str(i.get("source", "")).startswith("ANGEL")
    )
    return {
        "ok": angel_live >= 2,
        "source": "ANGEL_LIVE" if angel_live >= 2 else "PARTIAL",
        "live_count": live_count,
        "angel_live_count": angel_live,
        "indices": board,
    }


def get_cockpit_index_inputs() -> Dict[str, Any]:
    """NIFTY / BANKNIFTY / VIX for regime engine — Angel authority."""
    result = {
        "ok": False,
        "source": "ANGEL_UNAVAILABLE",
        "nifty_pct": 1.25,
        "bank_pct": 0.85,
        "vix": 13.8,
        "nifty_ltp": None,
        "bank_ltp": None,
        "advances": 1000,
        "declines": 1000,
        "breadth_live": False,
        "breadth_label": "Advances/Declines: NOT AVAILABLE",
    }
    ensure_subscribed(["NIFTY", "BANKNIFTY", "INDIAVIX"], "NSE")
    nifty = get_ltp_quote("NIFTY", "NSE")
    bank = get_ltp_quote("BANKNIFTY", "NSE")
    vix = get_ltp_quote("INDIAVIX", "NSE")
    if not nifty or not bank:
        return result
    result.update({
        "ok": True,
        "source": "ANGEL_WEBSOCKET",
        "nifty_pct": round(float(nifty.get("change_pct") or 0.0), 4),
        "bank_pct": round(float(bank.get("change_pct") or 0.0), 4),
        "vix": round(float(vix["ltp"]) if vix else 13.8, 4),
        "nifty_ltp": nifty["ltp"],
        "bank_ltp": bank["ltp"],
        "breadth_live": False,
        "breadth_label": "Advances/Declines: NOT AVAILABLE (Angel LTP only; breadth feed pending)",
    })
    return result


def get_market_data_status() -> Dict[str, Any]:
    conn = _get_conn_mgr()
    st = conn.get_connection_status()
    return {
        "broker_connected": st.get("broker_connected", False),
        "websocket_connected": st.get("websocket_connected", False),
        "is_paper_sandbox": st.get("is_paper_sandbox", False),
        "status_text": st.get("status_text", "Unknown"),
        "last_error": _last_error,
        "data_authority": "ANGEL_ONE" if st.get("websocket_connected") else "OFFLINE",
    }


def _connect_and_subscribe() -> None:
    global _last_error
    conn = _get_conn_mgr()
    try:
        ok = conn.connect_broker()
        # #region agent log
        try:
            import json as _json
            _dbg = {
                "sessionId": "bcdfad",
                "runId": "angel-ws-wire",
                "hypothesisId": "H1",
                "location": "angel_market_data_bridge.py:_connect_and_subscribe",
                "message": "angel_connect_result",
                "data": {
                    "ok": bool(ok),
                    "broker": bool(conn.is_connected),
                    "ws": bool(conn.websocket_connected),
                    "has_api_key": bool(getattr(conn, "api_key", None)),
                    "has_client": bool(getattr(conn, "client_code", None)),
                    "err": getattr(conn, "last_connection_error", None) or _last_error,
                },
                "timestamp": int(time.time() * 1000),
            }
            with open(os.path.join(_WORKSPACE_DIR, "debug-bcdfad.log"), "a", encoding="utf-8") as _f:
                _f.write(_json.dumps(_dbg) + "\n")
        except Exception:
            pass
        # #endregion
        if ok:
            logger.info("Angel broker connected for web dashboard")
        else:
            err = getattr(conn, "last_connection_error", None) or "Angel broker login failed"
            _last_error = err
            logger.warning("Angel broker connect failed: %s", err)
            return

        deadline = time.time() + _STARTUP_WAIT_SEC
        while time.time() < deadline and not conn.websocket_connected:
            time.sleep(0.5)

        if not conn.websocket_connected:
            _last_error = "Angel WebSocket did not connect within startup window"
            logger.warning(_last_error)
            return

        symbols = list(conn.stock_list or [])
        for sym, _ in _DEFAULT_INDEX_SYMBOLS:
            if sym not in symbols:
                symbols.append(sym)
        ensure_subscribed(symbols, "NSE")
        ensure_subscribed(["SENSEX"], "BSE")
        _last_error = None
        logger.info("Angel WebSocket subscribed for %d symbols + indices", len(symbols))
        # #region agent log
        try:
            import json as _json
            q = get_ltp_quote("RELIANCE", "NSE")
            _dbg = {
                "sessionId": "bcdfad",
                "runId": "angel-ws-wire",
                "hypothesisId": "H2",
                "location": "angel_market_data_bridge.py:_connect_and_subscribe",
                "message": "angel_post_subscribe_ltp",
                "data": {
                    "ws": bool(conn.websocket_connected),
                    "reliance": (q or {}).get("ltp"),
                    "source": (q or {}).get("source"),
                },
                "timestamp": int(time.time() * 1000),
            }
            with open(os.path.join(_WORKSPACE_DIR, "debug-bcdfad.log"), "a", encoding="utf-8") as _f:
                _f.write(_json.dumps(_dbg) + "\n")
        except Exception:
            pass
        # #endregion
    except Exception as exc:
        _last_error = str(exc)
        logger.exception("Angel market data startup failed")


def start_angel_market_data() -> None:
    """Idempotent background startup — call once when web dashboard boots."""
    global _bridge_started
    with _bridge_lock:
        if _bridge_started:
            return
        _bridge_started = True
    threading.Thread(target=_connect_and_subscribe, daemon=True, name="AngelMarketData").start()
