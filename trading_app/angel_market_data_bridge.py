"""
Angel One WebSocket + REST market data bridge for the web dashboard.

OIE-001: WebSocket = authoritative paper-execution price.
REST LTP = display/reference only. yfinance = research only.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

_WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, _WORKSPACE_DIR)

try:
    from trading_app.angel_log_redaction import install_angel_secret_redaction, redact_secrets
    install_angel_secret_redaction()
except Exception:
    def redact_secrets(text: str) -> str:  # type: ignore
        return str(text)

try:
    from trading_app.angel_rest_limiter import angel_rest_call, rest_in_cooldown, trip_rest_cooldown
except Exception:
    def angel_rest_call(label, fn, *, bypass_cooldown=False):  # type: ignore
        return fn()

    def rest_in_cooldown():  # type: ignore
        return False

    def trip_rest_cooldown(seconds=30.0, reason="rate_limit"):  # type: ignore
        pass

logger = logging.getLogger("AngelMarketDataBridge")

_WS_MAX_AGE_SEC = 15.0
_STARTUP_WAIT_SEC = 25.0
_IST = timezone(timedelta(hours=5, minutes=30))

# OIE-001 data-authority state machine
DATA_AUTHORITY_WS_LIVE = "ANGEL_WS_LIVE"
DATA_AUTHORITY_WS_STALE = "ANGEL_WS_STALE"
DATA_AUTHORITY_WS_DISCONNECTED = "ANGEL_WS_DISCONNECTED"
DATA_AUTHORITY_REST_REFERENCE = "ANGEL_REST_REFERENCE"
DATA_AUTHORITY_NO_VALID = "NO_VALID_MARKET_DATA"

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

_ALLOW_REST_FALLBACK = True  # Holdings/display need REST when WS is down or after hours
_EQUITY_REST_CACHE: Dict[str, Dict[str, Any]] = {}
_EQUITY_REST_CACHE_TTL = 45.0
_equity_rest_lock = threading.Lock()
_INDEX_REST_SYMBOLS = frozenset({"NIFTY", "BANKNIFTY", "INDIAVIX", "SENSEX", "NIFTY50", "FINNIFTY"})
_INDEX_REST_CACHE: Dict[str, Dict[str, Any]] = {}
_INDEX_REST_CACHE_TTL = 8.0
_index_rest_lock = threading.Lock()


def _get_conn_mgr():
    global _conn_mgr
    if _conn_mgr is None:
        from ui_new.connection_manager import get_connection_manager
        _conn_mgr = get_connection_manager()
    return _conn_mgr


def _iso_ist(epoch: Optional[float]) -> Optional[str]:
    if epoch is None or float(epoch) <= 0:
        return None
    return datetime.fromtimestamp(float(epoch), tz=_IST).isoformat(timespec="milliseconds")


def _ws_row(conn, symbol: str) -> Optional[Dict[str, Any]]:
    """Raw WS cache row for symbol (no freshness filter)."""
    sym = symbol.upper()
    with conn.ltp_lock:
        row = conn.ltp_data.get(sym)
        if not row:
            return None
        return dict(row)


def _ws_ltp(conn, symbol: str) -> Optional[Tuple[float, float, float]]:
    """Return (ltp, age_seconds, quote_ts_epoch) from WebSocket cache, or None if stale/missing."""
    row = _ws_row(conn, symbol)
    if not row:
        return None
    quote_ts = float(row.get("timestamp") or 0)
    if quote_ts <= 0:
        return None
    age = time.time() - quote_ts
    if age > _WS_MAX_AGE_SEC:
        return None
    ltp = float(row.get("ltp") or 0)
    if ltp <= 0:
        return None
    return ltp, age, quote_ts


def resolve_data_authority(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    OIE-001 explicit data-authority state machine.

    Paper execution is allowed only when authority == ANGEL_WS_LIVE and
    (if symbol given) that symbol has a fresh tick.
    """
    conn = _get_conn_mgr()
    st = conn.get_connection_status()
    broker = bool(st.get("broker_connected"))
    ws_transport = bool(st.get("websocket_connected"))
    streaming = bool(st.get("websocket_streaming"))
    auth_err = bool(st.get("broker_auth_error"))
    last_tick_age = st.get("last_tick_age_sec")

    symbol_fresh = None
    symbol_age = None
    if symbol:
        ws = _ws_ltp(conn, symbol.upper())
        symbol_fresh = ws is not None
        if ws:
            symbol_age = ws[1]
        else:
            row = _ws_row(conn, symbol.upper())
            if row and float(row.get("timestamp") or 0) > 0:
                symbol_age = time.time() - float(row["timestamp"])

    if auth_err or not broker:
        authority = DATA_AUTHORITY_NO_VALID
    elif not ws_transport:
        authority = DATA_AUTHORITY_WS_DISCONNECTED
    elif not streaming:
        authority = DATA_AUTHORITY_WS_STALE
    elif symbol and not symbol_fresh:
        # Global feed may be live (e.g. NIFTY) but this instrument is stale
        authority = DATA_AUTHORITY_WS_STALE
    elif streaming:
        authority = DATA_AUTHORITY_WS_LIVE
    else:
        authority = DATA_AUTHORITY_NO_VALID

    paper_allowed = authority == DATA_AUTHORITY_WS_LIVE and (
        symbol_fresh if symbol else True
    )

    return {
        "data_authority": authority,
        "paper_execution_allowed": bool(paper_allowed),
        "broker_connected": broker,
        "websocket_connected": ws_transport,
        "websocket_streaming": streaming,
        "broker_auth_error": auth_err,
        "last_tick_age_sec": last_tick_age,
        "symbol": symbol.upper() if symbol else None,
        "symbol_fresh": symbol_fresh,
        "symbol_age_sec": round(symbol_age, 2) if symbol_age is not None else None,
        "rest_reference_ok": bool(broker and not auth_err),
        "ws_max_age_sec": _WS_MAX_AGE_SEC,
    }


def _rest_trading_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Angel ltpData expects NSE equity tradingsymbol with -EQ (indices/InvITs keep as-is)."""
    sym = symbol.upper().strip()
    exch = exchange.upper()
    if exch != "NSE":
        return sym
    if sym in _INDEX_REST_SYMBOLS:
        return sym
    if "-" in sym:  # already IRBINVIT-IV, BAJAJ-AUTO, etc.
        return sym
    return f"{sym}-EQ"


def _rest_ltp(conn, symbol: str, exchange: str = "NSE") -> Optional[Dict[str, Any]]:
    """Angel REST ltpData — authenticated exchange quote (display/reference only)."""
    if not conn.smart_api or not conn.is_connected or getattr(conn, "is_paper_sandbox", False):
        return None
    if rest_in_cooldown():
        return None
    conn.ensure_tokens_loaded()
    sym = symbol.upper()
    exch = exchange.upper()
    key = f"{exch}:{sym}"
    token = conn.token_map.get(key)
    if not token and exch == "NSE" and not sym.endswith("-EQ") and "-" not in sym:
        token = conn.token_map.get(f"NSE:{sym}-EQ")
    if not token and "-" in sym:
        root = sym.rsplit("-", 1)[0]
        token = conn.token_map.get(f"{exch}:{root}") or conn.token_map.get(f"{exch}:{sym}")
    if not token:
        return None
    trade_sym = _rest_trading_symbol(sym, exch)

    def _call():
        resp = conn.smart_api.ltpData(exch, trade_sym, token)
        if (not resp or not resp.get("status")) and trade_sym != sym:
            return conn.smart_api.ltpData(exch, sym, token)
        return resp

    try:
        resp = angel_rest_call(f"ltp:{exch}:{sym}", _call)
        if not resp or not resp.get("status"):
            msg = str((resp or {}).get("message") or "")
            err = str((resp or {}).get("errorCode") or (resp or {}).get("errorcode") or "")
            blob = f"{msg} {err}"
            low = blob.lower()
            if "invalid api key" in low or "ag8004" in low:
                trip_rest_cooldown(
                    300.0,
                    "AG8004 Invalid API Key — whitelist public IP on Trading app / verify ANGEL_API_KEY",
                )
            elif "access" in low or "rate" in low or "too many" in low:
                trip_rest_cooldown(45.0, msg[:120] or err[:120])
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
            "data_authority": DATA_AUTHORITY_REST_REFERENCE,
            "instrument_token": str(token),
        }
    except Exception as exc:
        logger.warning("Angel REST LTP failed for %s:%s — %s", exch, trade_sym, redact_secrets(str(exc)))
        return None


def _equity_rest_cached(conn, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
    """Short-lived REST cache for equities (avoids blocking HTTPServer on every poll)."""
    sym = symbol.upper()
    if sym in _INDEX_REST_SYMBOLS:
        return None
    cache_key = f"{exchange.upper()}:{sym}"
    now = time.time()
    with _equity_rest_lock:
        hit = _EQUITY_REST_CACHE.get(cache_key)
        if hit and (now - float(hit.get("_ts") or 0)) < _EQUITY_REST_CACHE_TTL:
            return {k: v for k, v in hit.items() if k != "_ts"}
    rest = _rest_ltp(conn, sym, exchange)
    if not rest and exchange.upper() == "NSE":
        # BSE fallback for dual-listed / InvIT quirks
        rest = _rest_ltp(conn, sym, "BSE")
    if not rest:
        return None
    with _equity_rest_lock:
        _EQUITY_REST_CACHE[cache_key] = {**rest, "_ts": now}
    return rest


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
    Angel quote: WebSocket cache first, then authenticated REST (last close after hours).

    Returns None if no authenticated quote is available.
    """
    conn = _get_conn_mgr()
    sym = symbol.upper()
    exch = exchange.upper()

    # Index symbols: prefer REST so change_pct vs previous close is accurate.
    # WebSocket ticks carry LTP only (change_pct would otherwise stay 0.0 forever).
    if sym in _INDEX_REST_SYMBOLS:
        idx_rest = _index_rest_cached(conn, sym, exch)
        if idx_rest:
            idx_rest["live"] = True
            idx_rest["age_sec"] = 0.0
            return idx_rest

    ws = _ws_ltp(conn, sym)
    if ws:
        ltp, age, quote_ts = ws
        row = _ws_row(conn, sym) or {}
        close_px = float(row.get("closed_price") or 0)
        change_pct = float(row.get("change_pct") or 0.0)
        if close_px > 0 and ltp > 0 and abs(change_pct) < 1e-12:
            change_pct = ((ltp - close_px) / close_px) * 100.0
        return {
            "ltp": ltp,
            "change_pct": round(change_pct, 4),
            "source": "ANGEL_WEBSOCKET",
            "exchange": exch,
            "age_sec": round(age, 2),
            "quote_ts": quote_ts,
            "closed_price": close_px if close_px > 0 else None,
            "volume": int(row.get("volume") or 0),
            "has_prev_close": close_px > 0,
            "live": True,
        }

    idx_rest = _index_rest_cached(conn, sym, exch)
    if idx_rest:
        idx_rest["live"] = True
        idx_rest["age_sec"] = 0.0
        return idx_rest

    if _ALLOW_REST_FALLBACK:
        rest = _equity_rest_cached(conn, sym, exch)
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
    Fail-closed gate for paper execution (OIE-001).

    Requires ANGEL_WS_LIVE + symbol-specific tick age ≤ 15s.
    REST must never become paper execution authority.
    """
    ensure_subscribed([symbol.upper()], exchange)
    conn = _get_conn_mgr()
    auth = resolve_data_authority(symbol.upper())
    received_ts = time.time()
    row = _ws_row(conn, symbol.upper())
    ws = _ws_ltp(conn, symbol.upper())

    if auth.get("paper_execution_allowed") and ws:
        ltp, age, quote_ts = ws
        if ltp <= 0 or age > _WS_MAX_AGE_SEC:
            return False, None, (
                f"WebSocket LTP for {symbol.upper()} failed freshness/price checks "
                f"(ltp={ltp}, age={age:.1f}s, max={_WS_MAX_AGE_SEC:.0f}s)."
            )
        token = str((row or {}).get("token") or "")
        close_px = float((row or {}).get("closed_price") or 0)
        change_pct = float((row or {}).get("change_pct") or 0.0)
        if close_px > 0 and ltp > 0 and abs(change_pct) < 1e-12:
            change_pct = ((ltp - close_px) / close_px) * 100.0
        return True, {
            "ltp": ltp,
            "change_pct": round(change_pct, 4),
            "source": "ANGEL_WEBSOCKET",
            "price_source": "ANGEL_WEBSOCKET",
            "exchange": exchange.upper(),
            "instrument_token": token or None,
            "age_sec": round(age, 2),
            "quote_age_ms": int(round(age * 1000)),
            "quote_ts": quote_ts,
            "quote_timestamp": _iso_ist(quote_ts),
            "received_timestamp": _iso_ist(received_ts),
            "websocket_connected": True,
            "websocket_streaming": True,
            "data_authority": DATA_AUTHORITY_WS_LIVE,
            "data_quality": "VALID",
            "closed_price": close_px if close_px > 0 else None,
            "volume": int((row or {}).get("volume") or 0),
            "live": True,
        }, ""

    authority = auth.get("data_authority") or DATA_AUTHORITY_NO_VALID
    err = (_last_error or auth.get("last_connection_error") or "")
    if authority == DATA_AUTHORITY_NO_VALID or not auth.get("broker_connected"):
        detail = f" ({err})" if err else ""
        return False, None, (
            "Live Angel One broker is not connected or auth failed. Check config.json "
            f"credentials and restart the dashboard.{detail} "
            f"[data_authority={authority}]"
        )
    if authority == DATA_AUTHORITY_WS_DISCONNECTED:
        return False, None, (
            f"Angel WebSocket disconnected — paper execution blocked for {symbol.upper()}. "
            f"[data_authority={authority}]"
        )
    if authority == DATA_AUTHORITY_WS_STALE:
        age_note = auth.get("symbol_age_sec")
        return False, None, (
            f"Angel tick stale for {symbol.upper()} "
            f"(symbol_age={age_note}s, global_age={auth.get('last_tick_age_sec')}s, "
            f"max={_WS_MAX_AGE_SEC:.0f}s). Paper blocked — fail closed. "
            f"[data_authority={authority}]"
        )
    return False, None, (
        f"No fresh Angel WebSocket LTP for {symbol.upper()} "
        f"(max age {_WS_MAX_AGE_SEC:.0f}s). "
        "Paper trade blocked — REST/last-close quotes are not valid fill prices. "
        f"[data_authority={authority}]"
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
    """Subscribe symbols on Angel WebSocket if the socket is actually alive."""
    conn = _get_conn_mgr()
    alive = False
    try:
        checker = getattr(conn, "_ws_socket_alive", None)
        alive = bool(checker()) if callable(checker) else bool(conn.websocket_connected)
    except Exception:
        alive = bool(conn.websocket_connected)
    if not alive:
        # Do not flip connected→dead here (race with on_open). Just request reconnect.
        sched = getattr(conn, "_schedule_ws_reconnect", None)
        if callable(sched):
            sched()
        return
    pairs = [(s.upper(), exchange.upper()) for s in symbols if s]
    if pairs:
        conn.subscribe_symbols(pairs)


# Global indices for dashboard DISPLAY only (yfinance) — never paper-fill authority (OIE-001).
_GLOBAL_INDEX_SPECS = (
    ("NASDAQ", "^IXIC", "US"),
    ("S&P 500", "^GSPC", "US"),
    ("FTSE 100", "^FTSE", "UK"),
    ("NIKKEI 225", "^N225", "JP"),
    ("SHANGHAI COMP", "000001.SS", "CN"),
    ("STI", "^STI", "SG"),
    ("HANG SENG", "^HSI", "HK"),
    ("KOSPI", "^KS11", "KR"),
)

_GLOBAL_INDEX_CACHE: Dict[str, Any] = {"fetched_at": 0.0, "by_symbol": {}}
_GLOBAL_INDEX_CACHE_TTL = 120.0  # dashboard poll friendly; globals are delayed reference


def _fetch_global_index_quotes() -> Dict[str, Dict[str, Any]]:
    """yfinance quotes for global index strip (DISPLAY / RESEARCH only). Cached 120s."""
    now = time.time()
    age = now - float(_GLOBAL_INDEX_CACHE.get("fetched_at") or 0)
    cached = _GLOBAL_INDEX_CACHE.get("by_symbol") or {}
    if age < _GLOBAL_INDEX_CACHE_TTL and cached:
        return dict(cached)

    out: Dict[str, Dict[str, Any]] = {}
    try:
        import yfinance as yf
    except Exception:
        _GLOBAL_INDEX_CACHE["fetched_at"] = now
        _GLOBAL_INDEX_CACHE["by_symbol"] = {}
        return {}

    for name, ticker, exch in _GLOBAL_INDEX_SPECS:
        ltp = None
        chg = None
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                closes = hist["Close"].dropna()
                if len(closes) >= 1:
                    ltp = float(closes.iloc[-1])
                    prev = float(closes.iloc[-2]) if len(closes) >= 2 else ltp
                    chg = ((ltp - prev) / prev * 100.0) if prev else 0.0
        except Exception as exc:
            logger.debug("Global index %s (%s) failed: %s", name, ticker, exc)

        if ltp is not None and chg is not None:
            out[ticker] = {
                "name": name,
                "exchange": exch,
                "ltp": round(ltp, 2),
                "ltp_fmt": f"{ltp:,.2f}",
                "change_pct": round(chg, 2),
                "change_fmt": (f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"),
                "ok": True,
                "source": "YFINANCE_GLOBAL",
            }
        else:
            out[ticker] = {
                "name": name,
                "exchange": exch,
                "ltp": None,
                "ltp_fmt": "—",
                "change_pct": None,
                "change_fmt": "—",
                "ok": False,
                "source": "UNAVAILABLE",
            }

    _GLOBAL_INDEX_CACHE["fetched_at"] = now
    _GLOBAL_INDEX_CACHE["by_symbol"] = out
    return dict(out)


def get_index_board() -> Dict[str, Any]:
    """Index strip: Angel LTP for Indian indices; globals via yfinance (display only)."""
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

    global_quotes = _fetch_global_index_quotes()
    for name, ticker, exch in _GLOBAL_INDEX_SPECS:
        row = global_quotes.get(ticker) or {
            "name": name,
            "exchange": exch,
            "ltp": None,
            "ltp_fmt": "—",
            "change_pct": None,
            "change_fmt": "—",
            "ok": False,
            "source": "UNAVAILABLE",
        }
        # Ensure display name matches our board label
        row = dict(row)
        row["name"] = name
        row["exchange"] = exch
        board.append(row)
        if row.get("ok"):
            live_count += 1

    angel_live = sum(
        1 for i in board
        if i.get("ok") and str(i.get("source", "")).startswith("ANGEL")
    )
    global_live = sum(
        1 for i in board
        if i.get("ok") and str(i.get("source", "")).startswith("YFINANCE")
    )
    return {
        "ok": angel_live >= 2,
        "source": "ANGEL_LIVE" if angel_live >= 2 else "PARTIAL",
        "live_count": live_count,
        "angel_live_count": angel_live,
        "global_live_count": global_live,
        "indices": board,
    }


def get_cockpit_index_inputs() -> Dict[str, Any]:
    """NIFTY / BANKNIFTY / VIX (Angel) + NSE Advance/Decline breadth (display/regime)."""
    result: Dict[str, Any] = {
        "ok": False,
        "source": "ANGEL_UNAVAILABLE",
        "nifty_pct": None,
        "bank_pct": None,
        "vix": None,
        "nifty_ltp": None,
        "bank_ltp": None,
        "advances": None,
        "declines": None,
        "unchanged": None,
        "breadth_live": False,
        "breadth_index": None,
        "breadth_source": None,
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
        "source": nifty.get("source") or bank.get("source") or "ANGEL",
        "nifty_pct": round(float(nifty.get("change_pct") or 0.0), 4),
        "bank_pct": round(float(bank.get("change_pct") or 0.0), 4),
        "vix": round(float(vix["ltp"]), 4) if vix else None,
        "nifty_ltp": nifty["ltp"],
        "bank_ltp": bank["ltp"],
    })

    # NSE A/D — display/regime only (never paper-fill authority)
    try:
        from trading_app.nse_market_breadth import fetch_nse_advance_decline

        br = fetch_nse_advance_decline()
        if br.get("ok") and br.get("advances") is not None and br.get("declines") is not None:
            adv = int(br["advances"])
            dec = int(br["declines"])
            unch = int(br.get("unchanged") or 0)
            idx_name = str(br.get("index_name") or "NSE")
            result.update({
                "advances": adv,
                "declines": dec,
                "unchanged": unch,
                "breadth_live": True,
                "breadth_index": idx_name,
                "breadth_source": br.get("source") or "NSE_ALL_INDICES",
                "breadth_label": (
                    f"{adv} Advances / {dec} Declines"
                    f"{f' / {unch} Unchanged' if unch else ''}"
                    f" ({idx_name})"
                ),
            })
        else:
            result["breadth_label"] = (
                "Advances/Declines: NOT AVAILABLE "
                f"({br.get('error') or 'NSE breadth pending / pre-open'})"
            )
    except Exception as exc:
        logger.warning("NSE breadth attach failed: %s", exc)
        result["breadth_label"] = "Advances/Declines: NOT AVAILABLE (NSE breadth error)"

    return result


def get_market_data_status() -> Dict[str, Any]:
    conn = _get_conn_mgr()
    st = conn.get_connection_status()
    auth = resolve_data_authority()
    authority = auth.get("data_authority") or DATA_AUTHORITY_NO_VALID
    # REST reference is never paper authority; expose separately for UI
    if authority == DATA_AUTHORITY_WS_DISCONNECTED and auth.get("rest_reference_ok"):
        display_authority = DATA_AUTHORITY_REST_REFERENCE
    else:
        display_authority = authority
    return {
        "broker_connected": st.get("broker_connected", False),
        "websocket_connected": st.get("websocket_connected", False),
        "websocket_streaming": st.get("websocket_streaming", False),
        "last_tick_age_sec": st.get("last_tick_age_sec"),
        "broker_auth_error": st.get("broker_auth_error", False),
        "owns_broker_ws": st.get("owns_broker_ws", True),
        "ws_owner_pid": st.get("ws_owner_pid"),
        "is_paper_sandbox": st.get("is_paper_sandbox", False),
        "status_text": st.get("status_text", "Unknown"),
        "last_error": _last_error or st.get("last_connection_error"),
        "data_authority": display_authority,
        "paper_execution_allowed": bool(auth.get("paper_execution_allowed")),
        "ws_max_age_sec": _WS_MAX_AGE_SEC,
        "oie_exception": "7P-OBS-INTEGRITY-EXCEPTION-001",
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
