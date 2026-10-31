"""
Pre-Market Morning Brief helpers (display / research).

Builds market bias + focus list from Angel indices, NSE breadth, and analyzer
or watchlist movers. Never paper-fill authority (OIE-001).
"""

from __future__ import annotations

from datetime import time as dt_time
from typing import Any, Dict, List, Optional, Tuple


def classify_session_window(now_time: dt_time, *, weekday: int, market_open: bool) -> Tuple[str, str]:
    if weekday in (5, 6):
        return "WEEKEND", "Weekend — markets closed"
    if dt_time(7, 0) <= now_time < dt_time(9, 15):
        return "PRE_MARKET", "Pre-market window (07:00–09:15 IST)"
    if market_open:
        return "MARKET_OPEN", "Market open — morning brief still shown from live inputs"
    return "AFTER_HOURS", "Outside pre-market / session — last live snapshot"


def derive_market_bias(
    nifty_pct: Optional[float],
    bank_pct: Optional[float],
    vix: Optional[float] = None,
    *,
    advances: Optional[int] = None,
    declines: Optional[int] = None,
    breadth_live: bool = False,
) -> Tuple[str, str]:
    if nifty_pct is None or bank_pct is None:
        return "DATA UNAVAILABLE", "Waiting for Angel NIFTY / Bank NIFTY quotes."

    n = float(nifty_pct)
    b = float(bank_pct)
    v = float(vix) if vix is not None else None
    breadth_ratio = None
    if breadth_live and advances is not None and declines is not None and int(declines) > 0:
        breadth_ratio = float(advances) / float(declines)

    if v is not None and v > 24.0:
        return "CAUTIOUS / HIGH VOL", f"India VIX elevated at {v:.2f} — prefer defense until volatility cools."
    if n > 0.5 and (breadth_ratio is None or breadth_ratio > 1.2):
        detail = "NIFTY firm"
        if breadth_ratio is not None:
            detail += f"; breadth {advances}/{declines}"
        return "BULLISH BIAS", detail + "."
    if n < -0.5:
        return "BEARISH BIAS", "NIFTY soft — favor shorts / wait for confirmation."
    if abs(n) <= 0.35 and abs(b) <= 0.35:
        return "SIDEWAYS / RANGE", "Indices mixed/flat — mean-reversion setups more relevant than breakouts."
    return "MIXED / SELECTIVE", "Index direction not unanimous — stock-pick, avoid blanket bias."


def focus_from_analyzer_signals(signals: List[Dict[str, Any]], *, top_n: int = 5) -> List[Dict[str, Any]]:
    ranked = sorted(
        [s for s in (signals or []) if str(s.get("action") or "").upper() in ("BUY", "SELL")],
        key=lambda s: float(s.get("confidence") or 0),
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    for sig in ranked[:top_n]:
        sym = str(sig.get("symbol") or "").upper()
        if not sym:
            continue
        action = str(sig.get("action") or "").upper()
        conf = float(sig.get("confidence") or 0) * 100.0
        reason = str(sig.get("reason") or "Analyzer signal").strip()
        if len(reason) > 140:
            reason = reason[:137] + "…"
        out.append({
            "symbol": sym,
            "direction": action,
            "confidence_pct": round(conf, 1),
            "reason": f"{action} · {conf:.0f}% — {reason}",
            "source": "ANALYZER",
        })
    return out


def focus_from_watchlist_movers(
    symbols: List[str],
    live_map: Dict[str, Dict[str, Any]],
    *,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    movers = []
    for sym in symbols or []:
        key = str(sym).upper()
        q = live_map.get(key) or {}
        try:
            ltp = float(q.get("ltp") or 0)
            chg = float(q.get("change_pct") or 0)
        except (TypeError, ValueError):
            continue
        if ltp <= 0:
            continue
        movers.append((abs(chg), chg, key, ltp, str(q.get("source") or "ANGEL")))
    movers.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for _, chg, sym, ltp, src in movers[:top_n]:
        direction = "BUY" if chg >= 0 else "SELL"
        out.append({
            "symbol": sym,
            "direction": direction,
            "confidence_pct": None,
            "reason": (
                f"{direction} watch — Angel day change {chg:+.2f}% @ ₹{ltp:,.2f} "
                f"({src}). No analyzer signal yet."
            ),
            "source": "WATCHLIST_MOVERS",
        })
    return out
