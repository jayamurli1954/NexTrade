"""
Background watchlist scanner for Phase 7 Opportunities.

Historical candle fetch policy (desktop-parity / rate-limit safe):
  - Prefer local daily OHLC under research/data/feature_store/ohlc_cache/*.csv
    (same speed class as the old PyQt AnalyzerTab — no Angel candle storm).
  - Fall back to Angel ONE_DAY REST only on cache miss.
  - Live Angel LTP is still used only for BUY/SELL candidates (EnhancedAnalyzer).
  - Once per IST day on first launch; again on Rescan Watchlist.
  - Between scans, /api/opportunities serves cached signals + live LTP only.

Paper trading is unaffected — execution uses WebSocket LTP authority, not historical REST.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("OpportunityScanner")

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCAN_STATE_PATH = os.path.join(_root, "storage", "opportunity_scan_state.json")
_OHLC_CACHE_DIR = os.path.join(_root, "research", "data", "feature_store", "ohlc_cache")

_lock = threading.Lock()
_started = False
_scan_thread: Optional[threading.Thread] = None

# Cache
_signals: List[Dict[str, Any]] = []
_status: Dict[str, Any] = {
    "state": "idle",  # idle | scanning | ready | error
    "message": "Analyzer not started",
    "symbols_total": 0,
    "symbols_done": 0,
    "current_symbol": "",
    "signals_found": 0,
    "last_scan_ts": None,
    "last_scan_ist": None,
    "last_scan_date_ist": None,
    "scan_mode": "daily_once",  # daily_once | manual_rescan
    "error": None,
    "engine": "EnhancedAnalyzer",
}

# Align with EnhancedAnalyzer / analyzer_config confidence_threshold (0.60)
_MIN_CONFIDENCE = 0.60
_TOP_N = 10


def _load_local_daily_ohlc(symbol: str, period_days: int = 50):
    """
    Load daily OHLCV from feature-store disk cache (desktop-speed path).
    Returns a DataFrame with open/high/low/close/volume, or None on miss.
    """
    try:
        import pandas as pd
    except Exception:
        return None
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    path = os.path.join(_OHLC_CACHE_DIR, f"{sym}.csv")
    if not os.path.isfile(path):
        return None
    try:
        df = pd.read_csv(path)
        if df is None or df.empty:
            return None
        rename = {}
        for col in df.columns:
            key = str(col).strip().lower()
            if key in ("open", "high", "low", "close", "volume"):
                rename[col] = key
        if rename:
            df = df.rename(columns=rename)
        need = {"open", "high", "low", "close", "volume"}
        if not need.issubset(set(df.columns)):
            return None
        for col in need:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        # period_days is calendar-ish on Angel; local rows are trading days — keep enough bars
        take = max(int(period_days) or 50, 50)
        if len(df) < 30:
            return None
        out = df.tail(take).reset_index(drop=True)
        return out[["open", "high", "low", "close", "volume"]]
    except Exception as exc:
        logger.debug("local OHLC miss for %s: %s", sym, exc)
        return None


class _AngelHistDataProvider:
    """Adapter: local daily OHLC first, Angel fallback + LTP for EnhancedAnalyzer."""

    def __init__(self, conn):
        self._conn = conn
        self.local_hist_hits = 0
        self.angel_hist_hits = 0

    def get_ltp(self, symbol: str, exchange: str = "NSE"):
        try:
            from trading_app.angel_market_data_bridge import get_ltp_quote
            q = get_ltp_quote(symbol, exchange)
            if q and float(q.get("ltp") or 0) > 0:
                return float(q["ltp"])
        except Exception:
            pass
        # Fall back to connection manager (WS cache) — never invent sample prices here
        try:
            with self._conn.ltp_lock:
                row = self._conn.ltp_data.get(symbol.upper())
            if row and float(row.get("ltp") or 0) > 0:
                age = time.time() - float(row.get("timestamp") or 0)
                if age <= 60:
                    return float(row["ltp"])
        except Exception:
            pass
        return None

    def get_historical(self, symbol: str, exchange: str = "NSE", period_days: int = 50, **kwargs):
        """
        Default: ONE_DAY (local OHLC cache first).
        Explicit interval (e.g. FIVE_MINUTE for stop/target ATR) goes to Angel —
        do not force the 40-day floor or local daily CSV for intraday intervals.
        """
        interval = str(kwargs.get("interval") or "ONE_DAY").upper()
        if interval in ("ONE_DAY", "DAY", "1D", "D"):
            local = _load_local_daily_ohlc(symbol, period_days=max(int(period_days), 40))
            if local is not None and not local.empty:
                self.local_hist_hits += 1
                return local
            self.angel_hist_hits += 1
            return self._conn.get_historical(
                symbol=symbol,
                exchange=exchange,
                interval="ONE_DAY",
                period_days=max(int(period_days), 40),
            )
        # Intraday (candidates only) — narrow lookback, rate-limit-safe path
        try:
            from trading_app.angel_rest_limiter import rest_in_cooldown
            if rest_in_cooldown():
                return __import__("pandas").DataFrame()
        except Exception:
            pass
        self.angel_hist_hits += 1
        return self._conn.get_historical(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            period_days=max(int(period_days), 1),
        )


def get_scan_status() -> Dict[str, Any]:
    with _lock:
        return dict(_status)


def get_cached_signals() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(s) for s in _signals]


def _set_status(**kwargs) -> None:
    with _lock:
        _status.update(kwargs)


def _ist_now_str() -> str:
    try:
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).strftime("%d %b %Y %I:%M:%S %p IST")
    except Exception:
        return time.strftime("%Y-%m-%d %H:%M:%S")


def _ist_today() -> str:
    try:
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).strftime("%Y-%m-%d")
    except Exception:
        return time.strftime("%Y-%m-%d")


def _load_scan_state() -> bool:
    """Load persisted signals if today's IST scan has any saved progress (complete or partial)."""
    global _signals
    if not os.path.exists(_SCAN_STATE_PATH):
        logger.info("No opportunity scan cache on disk — morning historical scan will run")
        return False
    try:
        with open(_SCAN_STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        if str(payload.get("scan_date_ist") or "") != _ist_today():
            logger.info(
                "Opportunity scan cache is for %s (today %s) — morning scan will run",
                payload.get("scan_date_ist"),
                _ist_today(),
            )
            return False
        completed = bool(payload.get("scan_completed"))
        symbols_done = int(payload.get("symbols_done") or 0)
        symbols_total = int(payload.get("symbols_total") or 0)
        signals = list(payload.get("signals") or [])
        if not completed and symbols_done <= 0 and not signals:
            return False
        _signals = signals
        if completed:
            msg = (
                "Today's analyzer scan restored from disk — live LTP refreshed on demand. "
                "Click Rescan Watchlist to fetch fresh historical candles."
            )
        else:
            msg = (
                f"Partial scan restored ({symbols_done}/{symbols_total} symbols) — "
                "live LTP only. Click Rescan Watchlist to finish historical fetch."
            )
        _set_status(
            state="ready",
            message=msg,
            symbols_total=symbols_total,
            symbols_done=symbols_done,
            signals_found=int(payload.get("signals_found") or len(signals)),
            last_scan_ts=payload.get("last_scan_ts"),
            last_scan_ist=payload.get("last_scan_ist"),
            last_scan_date_ist=payload.get("scan_date_ist"),
            scan_mode=str(payload.get("scan_mode") or "daily_once"),
            error=None,
        )
        logger.info(
            "Restored %d cached opportunity signals for %s (%s, no historical rescan)",
            len(signals),
            _ist_today(),
            "complete" if completed else f"partial {symbols_done}/{symbols_total}",
        )
        return True
    except Exception as exc:
        logger.warning("Failed to load opportunity scan state: %s", exc)
        return False


def _save_scan_state(
    signals: List[Dict[str, Any]],
    *,
    symbols_total: int,
    symbols_done: int,
    scan_mode: str = "daily_once",
    scan_completed: bool = True,
) -> None:
    try:
        os.makedirs(os.path.dirname(_SCAN_STATE_PATH), exist_ok=True)
        payload = {
            "scan_date_ist": _ist_today(),
            "scan_completed": bool(scan_completed),
            "scan_mode": scan_mode,
            "last_scan_ts": time.time(),
            "last_scan_ist": _ist_now_str(),
            "symbols_total": symbols_total,
            "symbols_done": symbols_done,
            "signals_found": len(signals),
            "signals": signals,
        }
        tmp_path = _SCAN_STATE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, _SCAN_STATE_PATH)
    except Exception as exc:
        logger.warning("Failed to persist opportunity scan state: %s", exc)


def _wait_rest_ready(max_wait_sec: float = 120.0) -> None:
    """Block until Angel REST cooldown clears (or timeout) before historical scan."""
    try:
        from trading_app.angel_rest_limiter import rest_in_cooldown, rest_cooldown_remaining
    except Exception:
        return
    deadline = time.time() + float(max_wait_sec)
    while rest_in_cooldown() and time.time() < deadline:
        wait = float(rest_cooldown_remaining() or 0.0)
        _set_status(
            message=f"Waiting for Angel REST cooldown ({wait:.0f}s) before historical scan…",
        )
        time.sleep(min(wait + 1.0, 15.0))


def run_scan_once(max_symbols: Optional[int] = None, *, scan_mode: str = "daily_once") -> List[Dict[str, Any]]:
    """Synchronous watchlist scan — used by background loop and manual refresh."""
    from ui_new.connection_manager import get_connection_manager
    from analyzer.enhanced_analyzer import EnhancedAnalyzer

    conn = get_connection_manager()
    if not conn.is_connected:
        conn.load_config()
        conn.connect_broker()

    symbols = list(conn.stock_list or [])
    if not symbols:
        # Fallback: watchlist.json
        try:
            import json
            with open(os.path.join(_root, "watchlist.json"), "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                symbols = [str(s).upper() for s in raw]
            elif isinstance(raw, dict):
                symbols = [str(s).upper() for s in raw.keys()]
        except Exception as exc:
            logger.warning("watchlist load failed: %s", exc)

    symbols = [s for s in symbols if s and isinstance(s, str)]
    if max_symbols:
        symbols = symbols[: int(max_symbols)]

    local_ready = sum(
        1 for s in symbols if os.path.isfile(os.path.join(_OHLC_CACHE_DIR, f"{str(s).upper()}.csv"))
    )
    use_local_primary = local_ready >= max(1, int(0.8 * len(symbols))) if symbols else False

    # Only wait on Angel REST when we expect candle REST traffic (cache miss path).
    if not use_local_primary:
        _set_status(
            state="scanning",
            message="Waiting for Angel REST (rate-limit safe) before historical scan…",
            symbols_total=len(symbols),
            symbols_done=0,
            current_symbol="",
            signals_found=0,
            scan_mode=scan_mode,
            error=None,
        )
        _wait_rest_ready(max_wait_sec=180.0)

    hist_msg = (
        f"Scanning {len(symbols)} symbols via local daily OHLC "
        f"({local_ready}/{len(symbols)} cached) — Angel LTP for candidates only…"
        if use_local_primary
        else f"Scanning {len(symbols)} watchlist symbols (Angel ONE_DAY candles)…"
    )
    _set_status(
        state="scanning",
        message=hist_msg,
        symbols_total=len(symbols),
        symbols_done=0,
        current_symbol="",
        signals_found=0,
        scan_mode=scan_mode,
        error=None,
    )

    provider = _AngelHistDataProvider(conn)
    config_path = os.path.join(_root, "config.json")
    analyzer = EnhancedAnalyzer(provider, config_file=config_path if os.path.exists(config_path) else None)
    # Desktop AnalyzerTab paced ~0.5s/symbol (analyzer sleep) + 0.01s between.
    # Old web path forced 1.8–2.5s and waited 45s on every rate-limit → multi-hour scans.
    analyzer.rate_limit_sec = 0.05 if use_local_primary else 0.55
    original_sleep = time.sleep

    def _paced_sleep(sec):
        # Cap per-symbol delay inside analyze_symbol (normally 0.5s)
        if 0.4 <= float(sec) <= 0.6:
            return original_sleep(float(getattr(analyzer, "rate_limit_sec", 0.5)))
        return original_sleep(sec)

    try:
        from trading_app.angel_rest_limiter import rest_in_cooldown, rest_cooldown_remaining
    except Exception:
        rest_in_cooldown = lambda: False  # type: ignore
        rest_cooldown_remaining = lambda: 0.0  # type: ignore

    signals: List[Dict[str, Any]] = []
    symbols_done = 0
    scan_aborted = False
    cooldown_waits = 0
    try:
        time.sleep = _paced_sleep  # type: ignore
        for idx, sym in enumerate(symbols):
            # Local-primary scans barely touch Angel hist REST — don't abort on UI/other cooldowns.
            if rest_in_cooldown() and not use_local_primary:
                wait = float(rest_cooldown_remaining() or 0.0)
                cooldown_waits += 1
                _set_status(
                    current_symbol=str(sym).upper(),
                    message=f"Angel REST cooldown — pausing scan ({wait:.0f}s left) before {sym}",
                )
                if wait > 0:
                    original_sleep(min(wait + 1.0, 60.0))
                # Skip this symbol if still blocked — do not death-spiral retry into another 45s ban
                if rest_in_cooldown():
                    logger.warning("Skipping %s during Angel REST cooldown (continue scan)", sym)
                    symbols_done = idx + 1
                    continue
            try:
                _set_status(
                    current_symbol=str(sym).upper(),
                    message=f"Analyzing {sym} ({idx + 1}/{len(symbols)})…",
                )
                sig = analyzer.analyze_symbol(sym, "NSE")
                # Do not re-analyze the same symbol after a rate-limit trip — that re-bans Angel.
                if sig and float(sig.get("confidence") or 0) >= _MIN_CONFIDENCE:
                    if str(sig.get("action") or "").upper() in ("BUY", "SELL"):
                        signals.append(sig)
            except Exception as exc:
                logger.debug("scan skip %s: %s", sym, exc)

            symbols_done = idx + 1
            interim = sorted(signals, key=lambda x: float(x.get("confidence") or 0), reverse=True)[:_TOP_N]
            with _lock:
                global _signals
                _signals = interim

            pct = int(round(100.0 * symbols_done / max(len(symbols), 1)))
            _set_status(
                symbols_done=symbols_done,
                symbols_total=len(symbols),
                current_symbol=str(sym).upper(),
                signals_found=len(signals),
                message=(
                    f"Analyzed {symbols_done}/{len(symbols)} ({pct}%) — "
                    f"last {sym} — {len(signals)} signals"
                    + (
                        f" [local OHLC {provider.local_hist_hits}, Angel hist {provider.angel_hist_hits}]"
                        if (symbols_done % 10 == 0 or symbols_done == len(symbols))
                        else ""
                    )
                ),
            )

            # Persist every 5 symbols so same-day restart can skip historical rescan.
            if symbols_done % 5 == 0 or symbols_done == len(symbols):
                _save_scan_state(
                    interim,
                    symbols_total=len(symbols),
                    symbols_done=symbols_done,
                    scan_mode=scan_mode,
                    scan_completed=False,
                )
            # Tiny yield like desktop AnalyzerTab (0.01s) when on local path
            if use_local_primary:
                original_sleep(0.01)
    finally:
        time.sleep = original_sleep  # type: ignore

    logger.info(
        "Opportunity scan done: local_ohlc=%s angel_hist=%s cooldown_waits=%s signals=%s",
        provider.local_hist_hits,
        provider.angel_hist_hits,
        cooldown_waits,
        len(signals),
    )
    signals.sort(key=lambda x: float(x.get("confidence") or 0), reverse=True)
    top = signals[:_TOP_N]
    scan_completed = not scan_aborted and symbols_done >= len(symbols)

    with _lock:
        _signals = top

    if scan_completed:
        ready_msg = (
            f"Ready — top {len(top)} of {len(signals)} signals from {len(symbols)} stocks"
            f" (local OHLC {provider.local_hist_hits}, Angel hist {provider.angel_hist_hits}). "
            "Further polls use live LTP only until manual rescan."
        )
    else:
        ready_msg = (
            f"Partial — {symbols_done}/{len(symbols)} symbols analyzed, "
            f"{len(signals)} signals. Restart will not rescan; use Rescan Watchlist to continue."
        )

    _set_status(
        state="ready",
        message=ready_msg,
        symbols_total=len(symbols),
        symbols_done=symbols_done,
        current_symbol="",
        signals_found=len(signals),
        last_scan_ts=time.time(),
        last_scan_ist=_ist_now_str(),
        last_scan_date_ist=_ist_today(),
        scan_mode=scan_mode,
        error=None,
    )
    _save_scan_state(
        top,
        symbols_total=len(symbols),
        symbols_done=symbols_done,
        scan_mode=scan_mode,
        scan_completed=scan_completed,
    )
    if scan_completed:
        logger.info("Opportunity scan complete: %d signals (showing top %d)", len(signals), len(top))
    else:
        logger.warning(
            "Opportunity scan incomplete: %d/%d symbols, %d signals saved to disk",
            symbols_done,
            len(symbols),
            len(signals),
        )
    return top


def _loop() -> None:
    # Let broker login + WS settle; wait out any startup rate-limit cooldown.
    time.sleep(60.0)
    _wait_rest_ready(max_wait_sec=120.0)
    try:
        run_scan_once(scan_mode="daily_once")
    except Exception as exc:
        logger.exception("Opportunity scan failed")
        _set_status(state="error", message=f"Scan error: {exc}", error=str(exc))


def start_opportunity_scanner() -> None:
    """Idempotent background scanner — call once when dashboard boots."""
    global _started, _scan_thread
    with _lock:
        if _started:
            return
        _started = True

    # Same-day restart: hydrate in-memory signals immediately — no historical rescan.
    if _load_scan_state():
        logger.info("Opportunity scanner ready from persisted cache (restart during market hours)")
        return

    _set_status(state="starting", message="Analyzer starting — morning historical scan pending…")
    _scan_thread = threading.Thread(target=_loop, daemon=True, name="OpportunityScanner")
    _scan_thread.start()
    logger.info("Opportunity scanner thread started (first scan of the day)")


def request_rescan_async() -> bool:
    """User-initiated full historical rescan (only path besides first launch of the day)."""
    with _lock:
        if _status.get("state") == "scanning":
            return False
        _status.update(
            {
                "state": "scanning",
                "message": "Rescan starting — fetching historical candles…",
                "symbols_done": 0,
                "current_symbol": "",
                "signals_found": 0,
                "error": None,
            }
        )

    def _run():
        try:
            run_scan_once(scan_mode="manual_rescan")
        except Exception as exc:
            _set_status(state="error", message=str(exc), error=str(exc), current_symbol="")

    threading.Thread(target=_run, daemon=True, name="OpportunityRescan").start()
    return True
