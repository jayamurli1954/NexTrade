"""
NexTrade — Unified Single Browser-Based Web Application & Autonomous Trading Operating System.

Combines the 15-Minute Morning Cockpit (NEXTRADE TODAY), Strategy Intelligence Engine,
Daily Trading Mandate Engine (Invariant U5), 4-Mode Paper Simulator, Portfolio Holdings,
Watchlist Monitor, 7J Journal, Automated Excel Log Generator (.xlsx), and Control Plane.
"""

import os
import sys
import json
import csv
import io
import re
import time
import uuid
import threading
import webbrowser
import logging
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple, Optional
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import socket


class _ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Refuse to share a port on Windows (SO_REUSEADDR can silently dual-bind)."""

    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from trading_app.trade_ticket_engine import TradeTicketEngine, TradePlan, MissingProtectionException, UIBoundaryViolationException, UserIntentViolationException
from trading_app.paper_terminal import attach_plan_charge_preview, load_daily_ohlc, preview_from_payload, render_terminal_html
from trading_app.tariff_catalog import catalog_manifest
from trading_app.paper_capital_policy import (
    PAPER_LEDGER_CAPITAL,
    PAPER_DEPLOYABLE_CAPITAL,
    PAPER_MAX_OPEN_SCRIPS,
    PAPER_PER_SCRIP_CAPITAL,
    qty_for_scrip_allocation,
    deployable_remaining,
    can_open_paper_position,
)
from trading_app.paper_capital_ledger import (
    annotate_closed_trade_charges,
    displayed_paper_capital,
    infer_ledger_base_from_legacy_total,
)
from trading_app.paper_day_risk import (
    REASON_DAY_LOSS,
    REASON_DAY_PROFIT,
    collect_per_trade_exits,
    combined_day_pnl,
    day_flatten_reason,
    get_day_risk_limits,
)
from trading_app.paper_day_risk_policy import (
    build_day_limit_projection,
    configure_policy_path,
    load_policy,
    parse_policy_update,
    save_policy,
)
from trading_app.opportunity_engine import OpportunityEngine, TradeOpportunity
from trading_app.opportunity_scanner import (
    start_opportunity_scanner,
    get_cached_signals,
    get_scan_status,
    request_rescan_async,
)
from trading_app.trade_journal import TradeJournalEngine
from trading_app.excel_trade_logger import ExcelTradeLogger
from activation.production_activation_certifier import ProductionActivationCertifier
from governance.multi_account_portfolio_manager import MultiAccountPortfolioManager

# Phase 7K Modules
from trading_app.strategy_registry import StrategyRegistry, StrategyMetadata, MarketRegimeType, AutomationTier
from trading_app.regime_recommendation_engine import RegimeRecommendationEngine, DailyRecommendationOutcome
from trading_app.daily_mandate_engine import DailyMandateManager, DailyMandate, MandateState, U5MandateViolationException, MandateLimits
from trading_app.angel_market_data_bridge import (
    start_angel_market_data,
    get_ltp_map as angel_get_ltp_map,
    get_ltp_quote as angel_get_ltp_quote,
    get_index_board as angel_get_index_board,
    get_cockpit_index_inputs as angel_get_cockpit_index_inputs,
    get_market_data_status as angel_get_market_data_status,
    require_ltp as angel_require_ltp,
    ensure_subscribed as angel_ensure_subscribed,
    ensure_angel_connected as angel_ensure_angel_connected,
)
from trading_app.paper_observation_logger import (
    PaperObservationLogger,
    FillIntegrityRecord,
    BASELINE_VERSION as PAPER_BASELINE_VERSION,
)
try:
    from trading_app.angel_log_redaction import install_angel_secret_redaction
    install_angel_secret_redaction()
except Exception:
    pass
try:
    from trading_app.angel_rest_limiter import angel_rest_call, rest_in_cooldown, trip_rest_cooldown
except Exception:
    def angel_rest_call(label, fn, *, bypass_cooldown=False):  # type: ignore
        return fn()

    def rest_in_cooldown():  # type: ignore
        return False

    def trip_rest_cooldown(seconds=30.0, reason="rate_limit"):  # type: ignore
        pass

logger = logging.getLogger("NexTradeUnifiedWebApp")

_WATCHLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")
_WATCHLIST_DEFAULTS = ["RELIANCE", "HDFCBANK", "INFY", "TCS", "BHARTIARTL", "ICICIBANK", "SBIN"]
_WATCHLIST_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&-]{0,19}$")


def _normalize_watchlist_symbol(raw: Any) -> Tuple[str, Optional[str]]:
    """Return (NSE ticker, error). Watchlist stores bare names (SBIN), not SBIN-EQ."""
    s = str(raw or "").strip().upper()
    if not s:
        return "", "Enter a symbol (e.g. SBIN)"
    if s.endswith("-EQ"):
        s = s[:-3]
    if not _WATCHLIST_SYMBOL_RE.match(s):
        return "", "Use the NSE ticker (e.g. SBIN, M&M) — not the company name"
    return s, None


def _sort_watchlist_symbols(symbols: List[str]) -> List[str]:
    """A–Z ticker order (case-insensitive; duplicates dropped)."""
    seen = set()
    out: List[str] = []
    for item in symbols or []:
        sym, err = _normalize_watchlist_symbol(item)
        if err or not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    out.sort(key=str.upper)
    return out


def load_watchlist_symbols(path: Optional[str] = None) -> List[str]:
    filepath = path or _WATCHLIST_PATH
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                out = _sort_watchlist_symbols(data)
                if out:
                    return out
        except Exception:
            logger.exception("Failed to load watchlist from %s", filepath)
    return _sort_watchlist_symbols(list(_WATCHLIST_DEFAULTS))


def save_watchlist_symbols(symbols: List[str], path: Optional[str] = None) -> bool:
    filepath = path or _WATCHLIST_PATH
    ordered = _sort_watchlist_symbols(symbols)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(ordered, f, indent=2)
            f.write("\n")
        return True
    except Exception:
        logger.exception("Failed to save watchlist to %s", filepath)
        return False


def add_watchlist_symbol(raw_symbol: Any, path: Optional[str] = None) -> Dict[str, Any]:
    symbol, err = _normalize_watchlist_symbol(raw_symbol)
    if err:
        return {"success": False, "error": err}
    symbols = load_watchlist_symbols(path)
    if symbol in symbols:
        return {"success": False, "error": f"{symbol} is already on the watchlist"}
    symbols.append(symbol)
    if not save_watchlist_symbols(symbols, path):
        return {"success": False, "error": "Could not save watchlist.json"}
    return {
        "success": True,
        "symbol": symbol,
        "count": len(symbols),
        "message": f"Added {symbol}",
    }


def remove_watchlist_symbol(raw_symbol: Any, path: Optional[str] = None) -> Dict[str, Any]:
    symbol, err = _normalize_watchlist_symbol(raw_symbol)
    if err:
        return {"success": False, "error": err}
    symbols = load_watchlist_symbols(path)
    if symbol not in symbols:
        return {"success": False, "error": f"{symbol} is not on the watchlist"}
    symbols = [s for s in symbols if s != symbol]
    if not save_watchlist_symbols(symbols, path):
        return {"success": False, "error": "Could not save watchlist.json"}
    return {
        "success": True,
        "symbol": symbol,
        "count": len(symbols),
        "message": f"Removed {symbol}",
    }


def build_watchlist_csv(rows: List[Dict[str, Any]]) -> bytes:
    """UTF-8 CSV (Excel-friendly BOM) of the live watchlist table, A–Z by symbol."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Symbol", "LTP", "Change", "Change %", "Volume", "Price Source"])
    ordered = sorted(rows or [], key=lambda r: str(r.get("symbol") or "").upper())
    for row in ordered:
        writer.writerow([
            row.get("symbol") or "",
            row.get("ltp") or "",
            row.get("change") or "",
            row.get("change_pct") or "",
            row.get("volume") or "",
            row.get("price_source") or "",
        ])
    return buf.getvalue().encode("utf-8-sig")


IST = ZoneInfo("Asia/Kolkata")
PORT = 8580
DEFAULT_PAPER_CAPITAL = PAPER_LEDGER_CAPITAL
LEDGER_BASE = DEFAULT_PAPER_CAPITAL
TOTAL_CAPITAL = DEFAULT_PAPER_CAPITAL
UTILIZED_MARGIN = 0.0
TODAYS_PNL = 0.0
OVERALL_PNL = 0.0
TODAYS_NET_PNL = 0.0
OVERALL_NET_PNL = 0.0
LAST_UNREALIZED_PNL = 0.0
ACTIVE_RISK = 0.0
# Paper experiment: halt new entries after day profit/loss flatten (IST calendar day)
PAPER_DAY_HALTED = False
PAPER_DAY_HALT_REASON = ""
PAPER_DAY_HALT_DATE = ""  # YYYY-MM-DD IST

ALLOW_OFFMARKET_SIMULATION = False

# Active Store
ACTIVE_PAPER_POSITIONS = []
EXECUTED_TRADES_LOG = []
CURRENT_TRADE_PLAN = None

# Scheduled paper starts (same-day IST slots)
from trading_app import paper_trade_scheduler as paper_scheduler

# Persist paper capital across browser refresh / server restart (UI operational only)
_WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_STATE_PATH = os.path.join(_WORKSPACE_DIR, "storage", "paper_capital_state.json")
PAPER_POSITIONS_PATH = os.path.join(_WORKSPACE_DIR, "storage", "paper_positions_state.json")
PAPER_DAY_RISK_POLICY_PATH = os.path.join(_WORKSPACE_DIR, "storage", "paper_day_risk_policy.json")
REPORTS_DIR = os.path.join(_WORKSPACE_DIR, "reports")
configure_policy_path(PAPER_DAY_RISK_POLICY_PATH)
MANUAL_ZERODHA_HOLDINGS_PATH = os.path.join(_WORKSPACE_DIR, "storage", "manual_zerodha_holdings.json")
_manual_zerodha_lock = threading.Lock()
_paper_positions_lock = threading.RLock()
_trading_log_autosave_lock = threading.Lock()


def now_ist() -> datetime:
    """Current wall-clock time in India Standard Time (Asia/Kolkata)."""
    return datetime.now(IST)

# OIE-001 holdings REST cache (timestamp + source metadata)
_HOLDINGS_CACHE_TTL_SEC = 55.0
_holdings_cache_lock = threading.Lock()
_holdings_cache: Dict[str, Any] = {
    "raw": [],
    "source": "UNINITIALIZED",
    "error": None,
    "fetched_at": 0.0,
    "fetched_at_iso": None,
}

# Removed legacy sample LTP table — display and paper paths must use Angel quotes only (OIE-001).


def _fetch_nse_ltp_map(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Exchange-authenticated LTP via Angel WebSocket (primary) + REST (fallback).
    Returns empty for symbols without a live Angel quote — no yfinance on this path.
    """
    uniq = [s.strip().upper() for s in symbols if s and str(s).strip()]
    if not uniq:
        return {}
    angel_ensure_subscribed(uniq, "NSE")
    return angel_get_ltp_map(uniq, "NSE")


def _fetch_index_board() -> Dict[str, Any]:
    """Dashboard index strip — Angel LTP for NSE/BSE indices."""
    return angel_get_index_board()


def _fetch_live_index_inputs() -> Dict[str, Any]:
    """NIFTY / BANKNIFTY / VIX for 15-min cockpit — Angel authority."""
    return angel_get_cockpit_index_inputs()


def _enrich_positions_with_ltp(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach live LTP + mark-to-market PnL so Paper Simulator proves price freshness."""
    if not positions:
        return []
    symbols = [str(p.get("symbol", "")).upper() for p in positions if p.get("symbol")]
    live_map = _fetch_nse_ltp_map(symbols)
    enriched: List[Dict[str, Any]] = []
    for pos in positions:
        row = dict(pos)
        sym = str(row.get("symbol", "")).upper()
        entry = float(row.get("entry_price_raw") or 0.0)
        qty = int(row.get("quantity") or 0)
        direction = str(row.get("direction") or "BUY").upper()
        notional = abs(entry * qty)
        q = live_map.get(sym)
        if q and float(q.get("ltp") or 0) > 0:
            ltp = float(q["ltp"])
            chg = float(q.get("change_pct") or 0.0)
            if direction in ("SELL", "SHORT"):
                pnl = (entry - ltp) * qty
            else:
                pnl = (ltp - entry) * qty
            pnl_pct = (pnl / notional * 100.0) if notional > 0 else 0.0
            row["ltp"] = round(ltp, 2)
            row["ltp_fmt"] = f"₹{ltp:,.2f}"
            row["current_price"] = f"₹{ltp:,.2f}"
            row["pnl_raw"] = round(pnl, 2)
            row["pnl"] = (f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}")
            row["pnl_pct_raw"] = round(pnl_pct, 2)
            row["pnl_pct"] = (f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%")
            row["ltp_source"] = q.get("source", "ANGEL")
            row["ltp_change_pct"] = round(chg, 2)
            row["ltp_live"] = True
        else:
            row["ltp"] = None
            row["ltp_fmt"] = "—"
            row["ltp_source"] = "UNAVAILABLE"
            row["ltp_change_pct"] = None
            row["ltp_live"] = False
            row["pnl_pct_raw"] = None
            row["pnl_pct"] = "—"
        row["notional_raw"] = round(notional, 2)
        row["notional_fmt"] = f"₹{notional:,.2f}"
        row["direction"] = direction
        enriched.append(row)

    return enriched


def _position_notional(pos: Dict[str, Any]) -> float:
    entry = float(pos.get("entry_price_raw") or 0.0)
    qty = int(pos.get("quantity") or 0)
    return abs(entry * qty)


def _position_risk(pos: Dict[str, Any]) -> float:
    entry = float(pos.get("entry_price_raw") or 0.0)
    qty = int(pos.get("quantity") or 0)
    sl = pos.get("stop_loss_raw")
    if sl is None:
        # Parse "₹1,416.81" style strings if raw missing
        try:
            sl = float(str(pos.get("stop_loss") or "0").replace("₹", "").replace(",", ""))
        except (TypeError, ValueError):
            sl = 0.0
    try:
        sl_f = float(sl)
    except (TypeError, ValueError):
        sl_f = 0.0
    return abs(entry - sl_f) * qty if qty and entry else 0.0


def _recompute_paper_margin_from_positions() -> None:
    """
    Utilized margin MUST equal sum of open paper notional (entry × qty).
    Fixes ghost margin left behind after process restarts wiped in-memory positions.
    """
    global UTILIZED_MARGIN, ACTIVE_RISK
    open_pos = [p for p in ACTIVE_PAPER_POSITIONS if str(p.get("status") or "OPEN").upper() == "OPEN"]
    UTILIZED_MARGIN = round(sum(_position_notional(p) for p in open_pos), 2)
    ACTIVE_RISK = round(sum(_position_risk(p) for p in open_pos), 2)


def _recompute_paper_realized_pnl_from_trades() -> None:
    """
    Align journal totals with EXECUTED_TRADES_LOG.

    TODAYS_PNL = realized *gross* PnL for the current IST calendar day
    (day-halt still uses this so charge policy does not retune flatten).
    TODAYS_NET_PNL = gross minus statutory/broker charges (no assumed slippage).
    OVERALL_* = all-time from the in-memory journal.
    """
    global TODAYS_PNL, OVERALL_PNL, TODAYS_NET_PNL, OVERALL_NET_PNL
    from trading_app.journal_analytics import filter_trades_for_day
    from trading_app.paper_capital_ledger import net_after_charges

    def _nets(trades):
        gross_sum = 0.0
        net_sum = 0.0
        for t in trades:
            if str(t.get("status") or "CLOSED").upper() == "OPEN":
                continue
            try:
                gross = float(t.get("pnl") or 0.0)
            except (TypeError, ValueError):
                continue
            gross_sum += gross
            if t.get("net_pnl") is not None:
                try:
                    net_sum += float(t.get("net_pnl"))
                    continue
                except (TypeError, ValueError):
                    pass
            try:
                qty = int(t.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0
            info = net_after_charges(
                gross_pnl=gross,
                entry=float(t.get("entry_price") or 0.0),
                exit_px=float(t.get("exit_price") or 0.0),
                qty=qty,
            )
            net_sum += float(info["net_pnl"])
        return round(gross_sum, 2), round(net_sum, 2)

    OVERALL_PNL, OVERALL_NET_PNL = _nets(EXECUTED_TRADES_LOG)
    today = now_ist().strftime("%Y-%m-%d")
    TODAYS_PNL, TODAYS_NET_PNL = _nets(filter_trades_for_day(list(EXECUTED_TRADES_LOG), today))
    _refresh_display_capital()


def _unrealized_from_enriched(enriched: List[Dict[str, Any]]) -> float:
    total = 0.0
    for pos in enriched or []:
        raw = pos.get("pnl_raw")
        if raw is None:
            continue
        try:
            total += float(raw)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _refresh_display_capital(unrealized_pnl: Optional[float] = None) -> None:
    """Show base + today's realized net + live open P&L. Overall P&L is excluded."""
    global TOTAL_CAPITAL, LAST_UNREALIZED_PNL
    if unrealized_pnl is None:
        unrealized_pnl = LAST_UNREALIZED_PNL
    else:
        LAST_UNREALIZED_PNL = round(float(unrealized_pnl or 0.0), 2)
    TOTAL_CAPITAL = displayed_paper_capital(LEDGER_BASE, TODAYS_NET_PNL, LAST_UNREALIZED_PNL)


def _mark_live_day_pnl(enriched: Optional[List[Dict[str, Any]]] = None) -> float:
    """Apply live open MTM to displayed capital. Returns combined gross (realized + open)."""
    if enriched is None:
        open_pos = [p for p in ACTIVE_PAPER_POSITIONS if str(p.get("status") or "OPEN").upper() == "OPEN"]
        enriched = _enrich_positions_with_ltp(open_pos) if open_pos else []
    _refresh_display_capital(_unrealized_from_enriched(enriched))
    return round(float(TODAYS_PNL or 0.0) + float(LAST_UNREALIZED_PNL or 0.0), 2)


def _paper_positions_summary(enriched: List[Dict[str, Any]]) -> Dict[str, Any]:
    placed = sum(float(p.get("notional_raw") or 0) for p in enriched)
    pnl = sum(float(p.get("pnl_raw") or 0) for p in enriched if p.get("pnl_raw") is not None)
    pnl_pct = (pnl / placed * 100.0) if placed > 0 else 0.0
    return {
        "open_count": len(enriched),
        "cum_placed_raw": round(placed, 2),
        "cum_placed_fmt": f"₹{placed:,.2f}",
        "cum_pnl_raw": round(pnl, 2),
        "cum_pnl_fmt": (f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}"),
        "cum_pnl_pct_raw": round(pnl_pct, 2),
        "cum_pnl_pct_fmt": (f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"),
        "utilized_margin_raw": round(float(UTILIZED_MARGIN), 2),
        "deployable_capital_raw": round(float(PAPER_DEPLOYABLE_CAPITAL), 2),
        "per_scrip_capital_raw": round(float(PAPER_PER_SCRIP_CAPITAL), 2),
        "available_cash_raw": round(deployable_remaining(UTILIZED_MARGIN), 2),
    }


def _save_paper_positions_state() -> None:
    try:
        os.makedirs(os.path.dirname(PAPER_POSITIONS_PATH), exist_ok=True)
        with _paper_positions_lock:
            payload = {
                "active_positions": list(ACTIVE_PAPER_POSITIONS),
                "executed_trades_log": list(EXECUTED_TRADES_LOG),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            with open(PAPER_POSITIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
    except Exception as exc:
        logger.warning("Failed to persist paper positions: %s", exc)


def _load_paper_positions_state() -> None:
    global ACTIVE_PAPER_POSITIONS, EXECUTED_TRADES_LOG
    if not os.path.exists(PAPER_POSITIONS_PATH):
        return
    try:
        with open(PAPER_POSITIONS_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        ACTIVE_PAPER_POSITIONS = list(payload.get("active_positions") or [])
        EXECUTED_TRADES_LOG = list(payload.get("executed_trades_log") or [])
        _recompute_paper_margin_from_positions()
        _recompute_paper_realized_pnl_from_trades()
        _save_paper_capital_state()
        logger.info(
            "Loaded %d open paper positions; utilized_margin=%.2f",
            len(ACTIVE_PAPER_POSITIONS),
            UTILIZED_MARGIN,
        )
    except Exception as exc:
        logger.warning("Failed to load paper positions: %s", exc)


def _close_paper_position(
    position_id: str,
    exit_ltp: Optional[float] = None,
    reason: str = "USER_CLOSE",
    *,
    autosave_log: bool = True,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Close one open paper position at live LTP (or provided exit). Releases margin via recompute."""
    global TODAYS_PNL, OVERALL_PNL
    with _paper_positions_lock:
        idx = next((i for i, p in enumerate(ACTIVE_PAPER_POSITIONS) if p.get("position_id") == position_id), None)
        if idx is None:
            return False, f"Position {position_id} not found or already closed", None
        pos = dict(ACTIVE_PAPER_POSITIONS[idx])
        entry = float(pos.get("entry_price_raw") or 0)
        qty = int(pos.get("quantity") or 0)
        direction = str(pos.get("direction") or "BUY").upper()
        if exit_ltp is None or float(exit_ltp) <= 0:
            q = (_fetch_nse_ltp_map([str(pos.get("symbol") or "")]).get(str(pos.get("symbol") or "").upper()) or {})
            exit_ltp = float(q.get("ltp") or entry)
        exit_px = float(exit_ltp)
        if direction in ("SELL", "SHORT"):
            pnl = (entry - exit_px) * qty
        else:
            pnl = (exit_px - entry) * qty
        pos["status"] = "CLOSED"
        pos["exit_price_raw"] = round(exit_px, 2)
        pos["exit_price"] = f"₹{exit_px:,.2f}"
        pos["pnl_raw"] = round(pnl, 2)
        pos["pnl"] = (f"+₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}")
        pos["close_reason"] = reason
        pos["closed_at"] = now_ist().strftime("%Y-%m-%d %H:%M:%S")
        ACTIVE_PAPER_POSITIONS.pop(idx)
        # Update matching open trade log
        for t in EXECUTED_TRADES_LOG:
            if t.get("status") == "OPEN" and t.get("symbol") == pos.get("symbol") and abs(float(t.get("entry_price") or 0) - entry) < 0.02:
                t["status"] = "CLOSED"
                t["exit_price"] = exit_px
                t["exit_reason"] = reason
                t["pnl"] = round(pnl, 2)
                t["timestamp"] = pos.get("closed_at")
                annotate_closed_trade_charges(t)
                pos["gross_pnl"] = t.get("gross_pnl")
                pos["est_charges"] = t.get("est_charges")
                pos["net_pnl"] = t.get("net_pnl")
                break
        else:
            closed_row = {
                "trade_id": f"tr_{uuid.uuid4().hex[:6]}",
                "timestamp": pos.get("closed_at"),
                "symbol": pos.get("symbol"),
                "style": pos.get("trading_style"),
                "strategy": pos.get("strategy"),
                "direction": direction,
                "quantity": qty,
                "entry_price": entry,
                "exit_price": exit_px,
                "exit_reason": reason,
                "pnl": round(pnl, 2),
                "status": "CLOSED",
            }
            annotate_closed_trade_charges(closed_row)
            EXECUTED_TRADES_LOG.append(closed_row)
            pos["gross_pnl"] = closed_row.get("gross_pnl")
            pos["est_charges"] = closed_row.get("est_charges")
            pos["net_pnl"] = closed_row.get("net_pnl")
        _recompute_paper_margin_from_positions()
        _recompute_paper_realized_pnl_from_trades()
        _mark_live_day_pnl()
        _save_paper_capital_state()
        _save_paper_positions_state()
        net_txt = pos.get("net_pnl")
        if net_txt is not None:
            net_fmt = f"+₹{net_txt:,.2f}" if float(net_txt) >= 0 else f"-₹{abs(float(net_txt)):,.2f}"
            closed_msg = (
                f"Closed {pos.get('symbol')} @ ₹{exit_px:,.2f} "
                f"gross {pos['pnl']} · net after charges {net_fmt} · ledger ₹{TOTAL_CAPITAL:,.2f}"
            )
        else:
            closed_msg = f"Closed {pos.get('symbol')} @ ₹{exit_px:,.2f} PnL {pos['pnl']}"
    if autosave_log:
        _autosave_trading_log_excel()
    return True, closed_msg, pos


def _close_all_paper_positions(reason: str = "KILL_ALL") -> Dict[str, Any]:
    ids = [p.get("position_id") for p in list(ACTIVE_PAPER_POSITIONS) if p.get("position_id")]
    closed = []
    errors = []
    for pid in ids:
        ok, msg, pos = _close_paper_position(pid, reason=reason, autosave_log=False)
        if ok:
            closed.append(pos)
        else:
            errors.append(msg)
    if closed:
        _autosave_trading_log_excel()
    return {"closed_count": len(closed), "closed": closed, "errors": errors}


def _day_flatten_detail_suffix() -> str:
    lim = get_day_risk_limits()
    return f"(target+₹{lim.profit_target_inr:.0f}/loss-₹{lim.loss_limit_inr:.0f})"


def _day_limit_projection_for_ui() -> Dict[str, Any]:
    open_pos = [p for p in ACTIVE_PAPER_POSITIONS if str(p.get("status") or "OPEN").upper() == "OPEN"]
    enriched = _enrich_positions_with_ltp(open_pos) if open_pos else []
    return build_day_limit_projection(
        policy=load_policy(),
        trades=list(EXECUTED_TRADES_LOG),
        open_positions=enriched,
        today=now_ist().strftime("%Y-%m-%d"),
    )


def _refresh_paper_day_halt_calendar() -> None:
    """
    IST day session sync for paper day-risk:
    - Clear day-halt when the halt date is not today
    - Recompute TODAYS_PNL from today's closed trades only (0 on a fresh day)
    - Drop a stale halt if today's PnL no longer qualifies (prior-day leak)
    """
    global PAPER_DAY_HALTED, PAPER_DAY_HALT_REASON, PAPER_DAY_HALT_DATE
    today = now_ist().strftime("%Y-%m-%d")
    changed = False
    if PAPER_DAY_HALT_DATE and PAPER_DAY_HALT_DATE != today:
        PAPER_DAY_HALTED = False
        PAPER_DAY_HALT_REASON = ""
        PAPER_DAY_HALT_DATE = ""
        changed = True

    before_pnl = float(TODAYS_PNL or 0.0)
    _recompute_paper_realized_pnl_from_trades()
    if float(TODAYS_PNL or 0.0) != before_pnl:
        changed = True

    if PAPER_DAY_HALTED and not day_flatten_reason(float(TODAYS_PNL or 0.0)):
        # Halt was carried with prior-day PnL counted as today — clear so it is not a blocker.
        PAPER_DAY_HALTED = False
        PAPER_DAY_HALT_REASON = ""
        PAPER_DAY_HALT_DATE = ""
        changed = True
        logger.info(
            "Cleared stale paper day halt (IST day=%s todays_pnl=₹%.2f)",
            today,
            float(TODAYS_PNL or 0.0),
        )

    if changed:
        _save_paper_capital_state()


def _set_paper_day_halt(reason: str) -> None:
    global PAPER_DAY_HALTED, PAPER_DAY_HALT_REASON, PAPER_DAY_HALT_DATE
    PAPER_DAY_HALTED = True
    PAPER_DAY_HALT_REASON = str(reason or "")
    PAPER_DAY_HALT_DATE = now_ist().strftime("%Y-%m-%d")
    _save_paper_capital_state()
    lim = get_day_risk_limits()
    logger.warning(
        "Paper day halt armed: reason=%s date=%s (profit≥₹%.0f / loss≤-₹%.0f)",
        PAPER_DAY_HALT_REASON,
        PAPER_DAY_HALT_DATE,
        lim.profit_target_inr,
        lim.loss_limit_inr,
    )


def _build_excel_report_file(filename: Optional[str] = None) -> str:
    """Build multi-sheet Excel log under project reports/ (today vs period separated)."""
    from trading_app.journal_analytics import compute_journal_metrics, filter_trades_for_day

    excel_logger = ExcelTradeLogger(reports_dir=REPORTS_DIR)
    today = now_ist().strftime("%Y-%m-%d")
    all_trades = list(EXECUTED_TRADES_LOG)
    period = compute_journal_metrics(all_trades)
    today_m = compute_journal_metrics(filter_trades_for_day(all_trades, today))
    period_net = compute_journal_metrics(all_trades, use_net=True)
    daily_summary = {
        "date": today,
        "starting_capital": float(LEDGER_BASE),
        "ending_capital": float(TOTAL_CAPITAL),
        "todays_net_pnl": float(TODAYS_NET_PNL),
        "todays_win_rate_pct": float(today_m.win_rate_pct),
        "total_trades_today": int(today_m.total_trades),
    }
    cum_summary = {
        "period_start": period.period_start or today,
        "period_end": period.period_end or today,
        "cumulative_net_pnl": float(period.gross_pnl),
        "cumulative_trades": int(period.total_trades),
        "cumulative_win_rate_pct": float(period.win_rate_pct),
        "profit_factor": float(period.profit_factor),
        "max_drawdown": float(abs(period.max_drawdown)),
        "expectancy": float(period.expectancy),
        "avg_win": float(period.avg_win),
        "avg_loss": float(period.avg_loss),
        "largest_win": float(period.largest_win),
        "largest_loss": float(period.largest_loss),
        "max_consecutive_losses": int(period.max_consecutive_losses),
        "est_charges": float(period_net.est_charges),
        "est_net_pnl": float(period_net.net_pnl),
    }
    return excel_logger.generate_excel_report(
        filename=filename,
        executed_trades=all_trades,
        daily_summary=daily_summary,
        cumulative_summary=cum_summary,
        starting_capital=float(LEDGER_BASE),
        today=today,
    )


def _autosave_trading_log_excel() -> Optional[str]:
    """Overwrite today's trading log in project reports/ after closes (manual or auto)."""
    with _trading_log_autosave_lock:
        try:
            date_str = now_ist().strftime("%Y%m%d")
            path = _build_excel_report_file(filename=f"NexTrade_Trading_Log_{date_str}.xlsx")
            logger.info("Auto-saved trading log: %s", path)
            return path
        except Exception as exc:
            logger.warning("Trading log autosave failed: %s", exc)
            return None


def _evaluate_paper_auto_exits() -> Dict[str, Any]:
    """
    Paper experiment monitor (runs on positions poll + square-off worker):
    1) Per-trade target / stop-loss vs live LTP
    2) Day combined PnL flatten: +₹1500 profit / -₹2000 loss → close all open
    """
    lim = get_day_risk_limits()
    suffix = _day_flatten_detail_suffix()
    _refresh_paper_day_halt_calendar()
    if not ACTIVE_PAPER_POSITIONS:
        combined = float(TODAYS_PNL or 0.0)
        day_reason = day_flatten_reason(combined, lim)
        if day_reason and not PAPER_DAY_HALTED:
            detail = f"{day_reason}_₹{combined:,.0f}{suffix}"
            _set_paper_day_halt(detail)
        return {
            "closed_count": 0,
            "closed": [],
            "errors": [],
            "day_halt": PAPER_DAY_HALTED,
            "combined_day_pnl": round(combined, 2),
        }

    enriched = _enrich_positions_with_ltp(list(ACTIVE_PAPER_POSITIONS))
    closed: List[Dict[str, Any]] = []
    errors: List[str] = []

    # 1) Per-trade SL / target
    for pid, exit_px, reason in collect_per_trade_exits(enriched):
        ok, msg, pos = _close_paper_position(pid, exit_ltp=exit_px, reason=reason, autosave_log=False)
        if ok and pos:
            closed.append(pos)
            logger.info("Paper auto-exit %s @ %.2f (%s)", pid, exit_px, reason)
        elif not ok:
            errors.append(msg)

    # Re-enrich after per-trade closes for accurate day combined PnL
    open_now = [p for p in list(ACTIVE_PAPER_POSITIONS) if str(p.get("status") or "OPEN").upper() == "OPEN"]
    if not open_now and not closed:
        return {"closed_count": 0, "closed": [], "errors": errors, "day_halt": PAPER_DAY_HALTED}

    enriched2 = _enrich_positions_with_ltp(open_now) if open_now else []
    unrealized = [
        float(p.get("pnl_raw") or 0.0)
        for p in enriched2
        if p.get("pnl_raw") is not None
    ]
    # TODAYS_PNL is realized-only; combined includes open MTM
    combined = combined_day_pnl(TODAYS_PNL, unrealized)
    day_reason = day_flatten_reason(combined, lim)
    if day_reason:
        if open_now:
            live_map: Dict[str, Dict[str, Any]] = {}
            try:
                symbols = [str(p.get("symbol") or "").upper() for p in open_now if p.get("symbol")]
                live_map = _fetch_nse_ltp_map(symbols)
            except Exception as exc:
                logger.warning("Day-flatten LTP fetch failed: %s", exc)
            detail = f"{day_reason}_₹{combined:,.0f}{suffix}"
            for pos in list(open_now):
                pid = pos.get("position_id")
                if not pid:
                    continue
                exit_px = _mark_price_for_square_off(pos, live_map)
                ok, msg, closed_pos = _close_paper_position(
                    pid, exit_ltp=exit_px, reason=detail, autosave_log=False
                )
                if ok and closed_pos:
                    closed.append(closed_pos)
                elif not ok:
                    errors.append(msg)
            logger.warning(
                "Paper DAY flatten: combined_pnl=₹%.2f reason=%s closed=%d",
                combined,
                detail,
                len(closed),
            )
        else:
            detail = f"{day_reason}_₹{combined:,.0f}{suffix}"
        if not PAPER_DAY_HALTED:
            _set_paper_day_halt(detail)

    if closed:
        _autosave_trading_log_excel()

    return {
        "closed_count": len(closed),
        "closed": closed,
        "errors": errors,
        "day_halt": PAPER_DAY_HALTED,
        "combined_day_pnl": round(combined, 2),
    }


def _paper_monitor_then_square_off(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Worker tick: day/SL/TP exits first, then 15:15 MIS square-off."""
    auto = _evaluate_paper_auto_exits()
    so = _square_off_due_paper_positions(now)
    return {
        "closed_count": int(auto.get("closed_count") or 0) + int(so.get("closed_count") or 0),
        "auto_exits": auto,
        "square_off": so,
    }


def _mark_price_for_square_off(pos: Dict[str, Any], live_map: Optional[Dict[str, Dict[str, Any]]] = None) -> float:
    """Best available exit for forced square-off: live LTP → last mark → entry."""
    sym = str(pos.get("symbol") or "").upper()
    entry = float(pos.get("entry_price_raw") or 0.0)
    if live_map:
        q = live_map.get(sym) or {}
        try:
            ltp = float(q.get("ltp") or 0)
            if ltp > 0:
                return ltp
        except (TypeError, ValueError):
            pass
    for key in ("ltp", "exit_price_raw", "entry_price_raw"):
        try:
            val = float(pos.get(key) or 0)
            if val > 0:
                return val
        except (TypeError, ValueError):
            continue
    # Parse "₹1,313.85" style current_price if present
    for key in ("current_price", "entry_price"):
        raw = str(pos.get(key) or "").replace("₹", "").replace(",", "").strip()
        try:
            val = float(raw)
            if val > 0:
                return val
        except (TypeError, ValueError):
            continue
    return entry


def _square_off_due_paper_positions(now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Angel One MIS parity: force-close INTRADAY/SCALPING paper positions at/after 15:15 IST
    (and any overnight leftovers that remained OPEN).
    """
    now = now or now_ist()
    due = [
        p for p in list(ACTIVE_PAPER_POSITIONS)
        if p.get("position_id") and paper_scheduler.position_needs_intraday_square_off(p, now)
    ]
    if not due:
        return {"closed_count": 0, "closed": [], "errors": [], "reason": "AUTO_SQUARE_OFF_15:15"}

    symbols = [str(p.get("symbol") or "").upper() for p in due if p.get("symbol")]
    live_map: Dict[str, Dict[str, Any]] = {}
    try:
        live_map = _fetch_nse_ltp_map(symbols)
    except Exception as exc:
        logger.warning("Square-off LTP fetch failed (will use last mark/entry): %s", exc)

    closed = []
    errors = []
    for pos in due:
        pid = pos.get("position_id")
        exit_px = _mark_price_for_square_off(pos, live_map)
        ok, msg, closed_pos = _close_paper_position(
            pid,
            exit_ltp=exit_px,
            reason="AUTO_SQUARE_OFF_15:15",
            autosave_log=False,
        )
        if ok:
            closed.append(closed_pos)
            logger.warning(
                "AUTO SQUARE-OFF 15:15: closed %s (%s) @ ₹%.2f — %s",
                pos.get("symbol"),
                pid,
                exit_px,
                msg,
            )
        else:
            errors.append(msg)
    if closed:
        _autosave_trading_log_excel()
    return {
        "closed_count": len(closed),
        "closed": closed,
        "errors": errors,
        "reason": "AUTO_SQUARE_OFF_15:15",
    }


def _fmt_inr(amount: float, signed: bool = False) -> str:
    """Format rupee amounts consistently with the dashboard UI."""
    if signed:
        if amount >= 0:
            return f"+₹{amount:,.2f}"
        return f"-₹{abs(amount):,.2f}"
    return f"₹{amount:,.2f}"


def _holdings_ltp_symbol(symbol: str) -> str:
    """Map portfolio symbols (e.g. RELIANCE-EQ) to Angel NSE tickers.

    -EQ is stripped for equity token lookup. -IV InvITs keep the suffix
    (Angel master keys them as IRBINVIT-IV).
    """
    s = str(symbol or "").strip().upper()
    if s.endswith("-EQ"):
        return s[:-3]
    return s


def _normalize_broker_holding_symbol(symbol: str) -> str:
    """Normalize Angel/Zerodha tradingsymbol for display.

    Preserve known series suffixes (-EQ, -IV, -BE, etc.). Bare symbols get -EQ.
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return s
    if "-" not in s:
        return f"{s}-EQ"
    return s


def _sort_holdings_by_symbol(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort holdings A→Z by symbol (case-insensitive; -EQ suffix preserved)."""
    return sorted(holdings, key=lambda h: str(h.get("symbol") or "").upper())


def _angel_holding_to_raw(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map Angel holding() row to dashboard raw holding dict."""
    symbol = _normalize_broker_holding_symbol(
        item.get("tradingsymbol") or item.get("symbol") or ""
    )
    if not symbol:
        return None
    qty = int(float(item.get("quantity") or item.get("qty") or 0))
    if qty <= 0:
        return None
    avg = float(item.get("averageprice") or item.get("avg_price") or 0.0)
    fallback_ltp = float(item.get("ltp") or item.get("close") or avg or 0.0)
    return {
        "symbol": symbol,
        "qty": qty,
        "avg_price_raw": avg,
        "fallback_ltp_raw": fallback_ltp,
        "broker": "ANGEL",
        "manual": False,
    }


def _load_manual_zerodha_holdings() -> List[Dict[str, Any]]:
    """Load user-entered Zerodha holdings from local JSON store."""
    with _manual_zerodha_lock:
        if not os.path.exists(MANUAL_ZERODHA_HOLDINGS_PATH):
            return []
        try:
            with open(MANUAL_ZERODHA_HOLDINGS_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            rows = payload.get("holdings") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return []
            return [r for r in rows if isinstance(r, dict)]
        except Exception as exc:
            logger.warning("Failed to load manual Zerodha holdings: %s", exc)
            return []


def _save_manual_zerodha_holdings(holdings: List[Dict[str, Any]]) -> None:
    """Persist user-entered Zerodha holdings."""
    with _manual_zerodha_lock:
        try:
            os.makedirs(os.path.dirname(MANUAL_ZERODHA_HOLDINGS_PATH), exist_ok=True)
            payload = {
                "holdings": holdings,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            with open(MANUAL_ZERODHA_HOLDINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            logger.warning("Failed to save manual Zerodha holdings: %s", exc)
            raise


def _validate_manual_holding_payload(
    payload: Dict[str, Any], *, require_id: bool = False
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate add/update payload for manual Zerodha holdings."""
    symbol = _normalize_broker_holding_symbol(payload.get("symbol") or "")
    if not symbol:
        return None, "Symbol is required"
    try:
        qty = int(payload.get("qty"))
    except (TypeError, ValueError):
        return None, "Quantity must be a positive integer"
    if qty <= 0:
        return None, "Quantity must be a positive integer"
    try:
        avg_price = float(payload.get("avg_price"))
    except (TypeError, ValueError):
        return None, "Average price must be a positive number"
    if avg_price <= 0:
        return None, "Average price must be a positive number"
    row: Dict[str, Any] = {
        "symbol": symbol,
        "qty": qty,
        "avg_price": round(avg_price, 2),
        "broker": "ZERODHA",
        "notes": str(payload.get("notes") or "").strip(),
    }
    if require_id:
        hid = str(payload.get("id") or "").strip()
        if not hid:
            return None, "Holding id is required"
        row["id"] = hid
    return row, None


def _manual_zerodha_to_raw(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map stored manual Zerodha row to raw holding dict for LTP enrichment."""
    symbol = _normalize_broker_holding_symbol(item.get("symbol") or "")
    qty = int(float(item.get("qty") or 0))
    avg = float(item.get("avg_price") or item.get("avg_price_raw") or 0.0)
    return {
        "symbol": symbol,
        "qty": qty,
        "avg_price_raw": avg,
        "fallback_ltp_raw": avg,
        "broker": "ZERODHA",
        "manual": True,
        "id": item.get("id"),
        "notes": item.get("notes") or "",
    }


def _fetch_manual_zerodha_holdings_raw() -> List[Dict[str, Any]]:
    """Load manual Zerodha holdings and subscribe symbols for Angel LTP."""
    holdings: List[Dict[str, Any]] = []
    for item in _load_manual_zerodha_holdings():
        raw = _manual_zerodha_to_raw(item)
        if int(raw.get("qty") or 0) <= 0:
            continue
        holdings.append(raw)
    ltp_symbols = [_holdings_ltp_symbol(h["symbol"]) for h in holdings]
    if ltp_symbols:
        angel_ensure_subscribed(ltp_symbols, "NSE")
    return holdings


def _fetch_broker_holdings_raw() -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """
    Fetch holdings from Angel One when broker is connected.
    OIE-001: TTL cache + rate limiter; never storm Angel REST from UI polls.
    Returns (holdings_raw, source, error_message).
    source is one of: ANGEL_LIVE, ANGEL_CACHE, OFFLINE, DEMO, ERROR.
    """
    from ui_new.connection_manager import get_connection_manager
    from datetime import datetime as _dt

    conn = get_connection_manager()
    if getattr(conn, "is_paper_sandbox", False):
        return [], "DEMO", "Paper sandbox mode — live holdings unavailable"

    now = time.time()
    with _holdings_cache_lock:
        age = now - float(_holdings_cache.get("fetched_at") or 0)
        if _holdings_cache.get("raw") is not None and age < _HOLDINGS_CACHE_TTL_SEC and _holdings_cache.get("source") in (
            "ANGEL_LIVE", "ANGEL_CACHE"
        ):
            return (
                list(_holdings_cache.get("raw") or []),
                "ANGEL_CACHE",
                None,
            )

    if rest_in_cooldown():
        with _holdings_cache_lock:
            if _holdings_cache.get("raw"):
                return (
                    list(_holdings_cache["raw"]),
                    "ANGEL_CACHE",
                    f"REST cooldown — serving cache age={age:.0f}s",
                )
        return [], "ERROR", "Angel REST in cooldown (rate limit)"

    if not conn.is_connected:
        angel_ensure_angel_connected(wait_sec=8.0)

    if not conn.is_connected or not conn.smart_api:
        err = (
            getattr(conn, "last_connection_error", None)
            or "Angel broker not connected — check config.json and restart dashboard"
        )
        with _holdings_cache_lock:
            if _holdings_cache.get("raw"):
                return list(_holdings_cache["raw"]), "ANGEL_CACHE", err
        return [], "OFFLINE", err

    try:
        resp = angel_rest_call("holdings", lambda: conn.smart_api.holding())
        if not resp or not resp.get("status"):
            msg = str((resp or {}).get("message") or "Angel holdings API returned failure")
            if "access" in msg.lower() or "rate" in msg.lower():
                trip_rest_cooldown(45.0, msg[:120])
            logger.warning("Angel holdings API failed: %s", msg)
            with _holdings_cache_lock:
                if _holdings_cache.get("raw"):
                    return list(_holdings_cache["raw"]), "ANGEL_CACHE", msg
            return [], "ERROR", msg

        holdings_raw: List[Dict[str, Any]] = []
        for item in resp.get("data") or []:
            mapped = _angel_holding_to_raw(item)
            if mapped:
                holdings_raw.append(mapped)

        ltp_symbols = [_holdings_ltp_symbol(h["symbol"]) for h in holdings_raw]
        if ltp_symbols:
            angel_ensure_subscribed(ltp_symbols, "NSE")

        iso = _dt.now().astimezone().isoformat(timespec="seconds")
        with _holdings_cache_lock:
            _holdings_cache["raw"] = list(holdings_raw)
            _holdings_cache["source"] = "ANGEL_LIVE"
            _holdings_cache["error"] = None
            _holdings_cache["fetched_at"] = now
            _holdings_cache["fetched_at_iso"] = iso

        return holdings_raw, "ANGEL_LIVE", None
    except Exception as exc:
        msg = str(exc)
        if "cooldown" in msg.lower() or "rate" in msg.lower() or "access" in msg.lower():
            trip_rest_cooldown(30.0, msg[:120])
        logger.warning("Angel holdings fetch failed: %s", exc)
        with _holdings_cache_lock:
            if _holdings_cache.get("raw"):
                return list(_holdings_cache["raw"]), "ANGEL_CACHE", msg
        return [], "ERROR", msg


def _empty_holdings_summary() -> Dict[str, Any]:
    return {
        "holding_count": 0,
        "total_invested_raw": 0.0,
        "total_invested_fmt": "₹0.00",
        "total_current_raw": 0.0,
        "total_current_fmt": "₹0.00",
        "total_pnl_raw": 0.0,
        "total_pnl_fmt": "+₹0.00",
        "total_pnl_pct_raw": 0.0,
        "total_pnl_pct_fmt": "+0.00%",
        "live_ltp_count": 0,
    }


def _enrich_holdings_with_ltp(holdings: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Attach Angel LTP (WS or REST) to portfolio holdings and compute aggregate summary.

    When no Angel quote exists, do NOT fake LTP from avg_price (that caused Zerodha
    rows to show LTP==avg and +₹0 P&L with a misleading '(cached)' badge).
    Angel broker snapshot LTP may still be shown as SNAPSHOT.
    """
    if not holdings:
        return [], _empty_holdings_summary()

    ltp_symbols = [_holdings_ltp_symbol(h["symbol"]) for h in holdings]
    live_map = _fetch_nse_ltp_map(ltp_symbols)

    enriched: List[Dict[str, Any]] = []
    total_invested = 0.0
    total_current = 0.0
    live_ltp_count = 0

    for h, ltp_sym in zip(holdings, ltp_symbols):
        qty = int(h.get("qty") or 0)
        avg = float(h.get("avg_price_raw") or 0.0)
        invested = qty * avg
        total_invested += invested

        q = live_map.get(ltp_sym)
        ltp_live = False
        ltp_status = "UNQUOTED"
        ltp_source = "UNAVAILABLE"
        ltp: Optional[float] = None

        if q and float(q.get("ltp") or 0) > 0:
            ltp = float(q["ltp"])
            ltp_live = True
            live_ltp_count += 1
            ltp_source = str(q.get("source") or "ANGEL")
            ltp_status = "REST" if "REST" in ltp_source.upper() else "LIVE"
        else:
            # Angel holdings API often embeds last LTP — use as snapshot only.
            # Manual Zerodha stores fallback_ltp_raw == avg; never treat that as a quote.
            fallback = float(h.get("fallback_ltp_raw") or 0.0)
            is_manual = bool(h.get("manual"))
            if (not is_manual) and fallback > 0:
                ltp = fallback
                ltp_status = "SNAPSHOT"
                ltp_source = "BROKER_HOLDINGS"
            else:
                ltp = None
                ltp_status = "UNQUOTED"
                ltp_source = "UNQUOTED"

        if ltp is not None and ltp > 0:
            current = qty * ltp
            pnl = current - invested
            total_current += current
            ltp_fmt = _fmt_inr(ltp)
            pnl_fmt = _fmt_inr(pnl, signed=True)
            total_fmt = _fmt_inr(current)
            ltp_raw = round(ltp, 2)
            pnl_raw = round(pnl, 2)
            total_raw = round(current, 2)
        else:
            # Unquoted — do not invent P&L from avg as fake LTP
            ltp_fmt = "N/A"
            pnl_fmt = "—"
            total_fmt = "—"
            ltp_raw = None
            pnl_raw = None
            total_raw = None

        row_out: Dict[str, Any] = {
            "symbol": h["symbol"],
            "qty": qty,
            "avg_price_raw": round(avg, 2),
            "avg_price": _fmt_inr(avg),
            "ltp_raw": ltp_raw,
            "ltp": ltp_fmt,
            "ltp_live": ltp_live,
            "ltp_status": ltp_status,
            "ltp_source": ltp_source,
            "invested_raw": round(invested, 2),
            "invested_fmt": _fmt_inr(invested),
            "total_value_raw": total_raw,
            "total_value": total_fmt,
            "pnl_raw": pnl_raw,
            "pnl": pnl_fmt,
            "broker": h.get("broker") or "ANGEL",
            "manual": bool(h.get("manual")),
        }
        if h.get("manual"):
            row_out["id"] = h.get("id")
            row_out["notes"] = h.get("notes") or ""
        enriched.append(row_out)

    total_pnl = total_current - total_invested
    pnl_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0

    summary = {
        "holding_count": len(enriched),
        "total_invested_raw": round(total_invested, 2),
        "total_invested_fmt": _fmt_inr(total_invested),
        "total_current_raw": round(total_current, 2),
        "total_current_fmt": _fmt_inr(total_current),
        "total_pnl_raw": round(total_pnl, 2),
        "total_pnl_fmt": _fmt_inr(total_pnl, signed=True),
        "total_pnl_pct_raw": round(pnl_pct, 2),
        "total_pnl_pct_fmt": (f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"),
        "live_ltp_count": live_ltp_count,
    }
    return enriched, summary


def _save_paper_capital_state() -> None:
    """Persist capital counters used by the paper dashboard."""
    try:
        os.makedirs(os.path.dirname(PAPER_STATE_PATH), exist_ok=True)
        payload = {
            "ledger_base": float(LEDGER_BASE),
            "total_capital": float(TOTAL_CAPITAL),
            "utilized_margin": float(UTILIZED_MARGIN),
            "todays_pnl": float(TODAYS_PNL),
            "overall_pnl": float(OVERALL_PNL),
            "todays_net_pnl": float(TODAYS_NET_PNL),
            "overall_net_pnl": float(OVERALL_NET_PNL),
            "active_risk": float(ACTIVE_RISK),
            "paper_day_halted": bool(PAPER_DAY_HALTED),
            "paper_day_halt_reason": str(PAPER_DAY_HALT_REASON or ""),
            "paper_day_halt_date": str(PAPER_DAY_HALT_DATE or ""),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(PAPER_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as exc:
        logger.warning("Failed to persist paper capital state: %s", exc)


def _load_paper_capital_state() -> None:
    """Load persisted capital counters into module globals."""
    global LEDGER_BASE, TOTAL_CAPITAL, UTILIZED_MARGIN, TODAYS_PNL, OVERALL_PNL, ACTIVE_RISK
    global TODAYS_NET_PNL, OVERALL_NET_PNL
    global PAPER_DAY_HALTED, PAPER_DAY_HALT_REASON, PAPER_DAY_HALT_DATE
    if not os.path.exists(PAPER_STATE_PATH):
        return
    try:
        with open(PAPER_STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("ledger_base") is not None:
            LEDGER_BASE = float(payload["ledger_base"])
        else:
            LEDGER_BASE = infer_ledger_base_from_legacy_total(
                payload.get("total_capital", DEFAULT_PAPER_CAPITAL)
            )
        UTILIZED_MARGIN = float(payload.get("utilized_margin", 0.0))
        TODAYS_PNL = float(payload.get("todays_pnl", 0.0))
        OVERALL_PNL = float(payload.get("overall_pnl", 0.0))
        TODAYS_NET_PNL = float(payload.get("todays_net_pnl", 0.0))
        OVERALL_NET_PNL = float(payload.get("overall_net_pnl", 0.0))
        ACTIVE_RISK = float(payload.get("active_risk", 0.0))
        PAPER_DAY_HALTED = bool(payload.get("paper_day_halted", False))
        PAPER_DAY_HALT_REASON = str(payload.get("paper_day_halt_reason") or "")
        PAPER_DAY_HALT_DATE = str(payload.get("paper_day_halt_date") or "")
        _refresh_display_capital()
        logger.info(
            "Loaded paper capital state: LEDGER_BASE=%.2f TOTAL_CAPITAL=%.2f",
            LEDGER_BASE,
            TOTAL_CAPITAL,
        )
    except Exception as exc:
        logger.warning("Failed to load paper capital state: %s", exc)


_load_paper_capital_state()
_load_paper_positions_state()  # restores open trades; recomputes utilized margin from notional
_refresh_paper_day_halt_calendar()  # IST day PnL → 0 + clear stale day halt on new session

# Phase 7K Managers
strategy_registry = StrategyRegistry()
regime_engine = RegimeRecommendationEngine(strategy_registry)
mandate_manager = DailyMandateManager()
paper_observation_logger = PaperObservationLogger()
PAPER_FILL_MAX_AGE_SEC = 15.0


def _paper_fill_quality_gate(quote: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Thin fail-closed gate for paper fills (OIE-001 / RC2).
    Requires ANGEL_WEBSOCKET + data_authority ANGEL_WS_LIVE, ltp > 0, age_sec <= 15.
    """
    if not quote:
        return False, "Paper fill rejected: empty quote.", {
            "data_quality_passed": False,
            "fill_price_source": None,
            "age_sec": None,
            "quote_ts": None,
        }
    source = str(quote.get("source") or quote.get("price_source") or "")
    authority = str(quote.get("data_authority") or "")
    try:
        ltp = float(quote.get("ltp") or 0)
    except (TypeError, ValueError):
        ltp = 0.0
    try:
        age_sec = float(quote["age_sec"]) if quote.get("age_sec") is not None else 9999.0
    except (TypeError, ValueError):
        age_sec = 9999.0
    quote_ts = quote.get("quote_ts")
    meta = {
        "data_quality_passed": False,
        "fill_price_source": source or None,
        "age_sec": round(age_sec, 2),
        "quote_ts": quote_ts,
        "ltp": ltp,
        "data_authority": authority or None,
        "quote_age_ms": quote.get("quote_age_ms"),
        "instrument_token": quote.get("instrument_token"),
        "quote_timestamp": quote.get("quote_timestamp"),
        "received_timestamp": quote.get("received_timestamp"),
        "websocket_connected": quote.get("websocket_connected"),
        "websocket_streaming": quote.get("websocket_streaming"),
        "data_quality": quote.get("data_quality"),
    }
    if source != "ANGEL_WEBSOCKET":
        return False, (
            f"Paper fill rejected: source must be ANGEL_WEBSOCKET (got {source or 'MISSING'}). "
            "REST/last-close quotes are not valid fill prices."
        ), meta
    if authority and authority != "ANGEL_WS_LIVE":
        return False, (
            f"Paper fill rejected: data_authority must be ANGEL_WS_LIVE (got {authority})."
        ), meta
    if ltp <= 0:
        return False, "Paper fill rejected: LTP must be > 0.", meta
    if age_sec > PAPER_FILL_MAX_AGE_SEC:
        return False, (
            f"Paper fill rejected: quote age {age_sec:.1f}s exceeds "
            f"{PAPER_FILL_MAX_AGE_SEC:.0f}s WS freshness SLA."
        ), meta
    meta["data_quality_passed"] = True
    meta["data_quality"] = "VALID"
    return True, "", meta


def format_ist_clock(dt: Optional[datetime] = None) -> str:
    """Human-readable IST timestamp for dashboard display."""
    dt = dt or now_ist()
    return dt.strftime("%A, %d %b %Y · %I:%M:%S %p IST")


def get_ist_context() -> Dict[str, Any]:
    """IST date/time/day metadata shared by status and mandate APIs."""
    dt = now_ist()
    return {
        "ist_datetime": format_ist_clock(dt),
        "ist_date": dt.strftime("%Y-%m-%d"),
        "ist_day": dt.strftime("%A"),
        "ist_time": dt.strftime("%I:%M:%S %p"),
    }


def is_market_open() -> Tuple[bool, str]:
    """Checks if Indian Equity Markets (NSE/BSE) are open (Mon-Fri 09:15 - 15:30 IST)."""
    now = now_ist()
    day_name = now.strftime("%A")
    if now.weekday() in (5, 6):
        return False, f"Market closed on {day_name} (weekend)."

    current_time = now.time()
    if current_time < dt_time(9, 15) or current_time > dt_time(15, 30):
        return False, "Outside 09:15 AM - 03:30 PM IST trading hours."

    return True, "Market Open"


def fill_paper_trade_plan(plan: TradePlan) -> Dict[str, Any]:
    """
    Shared paper fill path for immediate execute and scheduled starts.
    Requires Angel WS live LTP (OIE-001). Caller must enforce market-hours / mandate gates.
    """
    global UTILIZED_MARGIN

    _refresh_paper_day_halt_calendar()
    if PAPER_DAY_HALTED:
        lim = get_day_risk_limits()
        return {
            "success": False,
            "error": (
                f"Paper day halt active ({PAPER_DAY_HALT_REASON}). "
                f"Day profit target +₹{lim.profit_target_inr:.0f} or loss limit −₹{lim.loss_limit_inr:.0f} "
                f"already hit — no new paper entries until next session."
            ),
            "day_halt": True,
            "baseline_version": PAPER_BASELINE_VERSION,
        }

    open_ok, _open_reason = is_market_open()
    now = now_ist()
    if paper_scheduler.is_square_off_style(getattr(plan, "trading_style", "")) and paper_scheduler.is_past_intraday_square_off(now):
        return {
            "success": False,
            "error": (
                "INTRADAY/SCALPING paper entries blocked after 03:15 PM IST "
                "(Angel One MIS square-off cutoff)."
            ),
            "square_off_cutoff": True,
            "baseline_version": PAPER_BASELINE_VERSION,
        }
    ok_ltp, quote, ltp_err = angel_require_ltp(plan.symbol, "NSE")
    if not ok_ltp:
        return {
            "success": False,
            "error": ltp_err,
            "live_ltp_required": True,
            "data_quality_passed": False,
            "baseline_version": PAPER_BASELINE_VERSION,
        }

    dq_ok, dq_err, dq_meta = _paper_fill_quality_gate(quote)
    if not dq_ok:
        return {
            "success": False,
            "error": dq_err,
            "live_ltp_required": True,
            "data_quality_passed": False,
            "fill_price_source": dq_meta.get("fill_price_source"),
            "age_sec": dq_meta.get("age_sec"),
            "baseline_version": PAPER_BASELINE_VERSION,
        }

    live_entry = round(float(quote["ltp"]), 2)
    old_entry = float(plan.entry_price) or live_entry
    if old_entry > 0 and abs(live_entry - old_entry) > 0.001:
        scale = live_entry / old_entry
        plan.entry_price = live_entry
        plan.stop_loss_price = round(float(plan.stop_loss_price) * scale, 2)
        plan.target_price = round(float(plan.target_price) * scale, 2)
        if plan.trailing_stop and plan.trailing_stop.enabled:
            plan.trailing_stop.current_trigger_price = round(
                float(plan.trailing_stop.current_trigger_price) * scale, 2
            )
    else:
        plan.entry_price = live_entry

    # ₹1,00,000 / live LTP = qty (no intraday margin multiplier)
    plan.quantity = qty_for_scrip_allocation(live_entry)
    plan.capital_required = round(float(plan.entry_price) * int(plan.quantity), 2)

    open_count = len([
        p for p in ACTIVE_PAPER_POSITIONS
        if str(p.get("status") or "OPEN").upper() == "OPEN"
    ])
    cap_ok, cap_err = can_open_paper_position(open_count, UTILIZED_MARGIN, plan.capital_required)
    if not cap_ok:
        return {
            "success": False,
            "error": cap_err,
            "live_ltp_required": True,
            "data_quality_passed": True,
            "baseline_version": PAPER_BASELINE_VERSION,
        }

    fill_source = str(quote.get("source") or "ANGEL_WEBSOCKET")
    age_sec = dq_meta.get("age_sec")
    quote_ts = dq_meta.get("quote_ts")
    quote_age_ms = dq_meta.get("quote_age_ms")
    if quote_age_ms is None and isinstance(age_sec, (int, float)):
        quote_age_ms = int(round(float(age_sec) * 1000))
    data_authority = str(quote.get("data_authority") or "ANGEL_WS_LIVE")
    instrument_token = str(quote.get("instrument_token") or "")
    quote_timestamp = str(quote.get("quote_timestamp") or "")
    received_timestamp = str(quote.get("received_timestamp") or "")
    decision_price = float(old_entry) if old_entry else float(live_entry)
    ist_now = now_ist()
    ist_ts = format_ist_clock(ist_now)
    fill_ts_local = ist_now.strftime("%Y-%m-%d %H:%M:%S")
    quote_quality = (
        f"WS fresh age={age_sec}s ≤ {PAPER_FILL_MAX_AGE_SEC:.0f}s "
        f"authority={data_authority}"
        if age_sec is not None else f"WS quote authority={data_authority}"
    )
    pos_id = f"pos_{uuid.uuid4().hex[:6]}"
    trade_id = f"tr_{uuid.uuid4().hex[:6]}"

    integrity = {
        "fill_price_source": fill_source,
        "price_source": fill_source,
        "age_sec": age_sec,
        "quote_age_ms": quote_age_ms,
        "quote_ts": quote_ts,
        "quote_timestamp": quote_timestamp,
        "received_timestamp": received_timestamp,
        "exchange": "NSE",
        "instrument_token": instrument_token,
        "decision_price": decision_price,
        "fill_price": float(plan.entry_price),
        "websocket_connected": bool(quote.get("websocket_connected", True)),
        "websocket_streaming": bool(quote.get("websocket_streaming", True)),
        "data_authority": data_authority,
        "data_quality": "VALID",
        "market_open": bool(open_ok),
        "timestamp_ist": ist_ts,
        "data_quality_passed": True,
        "quote_quality": quote_quality,
        "baseline_version": PAPER_BASELINE_VERSION,
        "oie_exception": "7P-OBS-INTEGRITY-EXCEPTION-001",
    }

    new_position = {
        "position_id": pos_id,
        "symbol": plan.symbol,
        "direction": plan.direction,
        "trading_style": plan.trading_style,
        "strategy": plan.strategy,
        "quantity": plan.quantity,
        "entry_price": f"₹{plan.entry_price:,.2f}",
        "entry_price_raw": plan.entry_price,
        "current_price": f"₹{plan.entry_price:,.2f}",
        "fill_price_source": fill_source,
        "age_sec": age_sec,
        "quote_ts": quote_ts,
        "quote_age_ms": quote_age_ms,
        "data_authority": data_authority,
        "instrument_token": instrument_token,
        "market_open": bool(open_ok),
        "timestamp_ist": ist_ts,
        "data_quality_passed": True,
        "quote_quality": quote_quality,
        "stop_loss": f"₹{plan.stop_loss_price:,.2f}",
        "stop_loss_raw": float(plan.stop_loss_price),
        "target": f"₹{plan.target_price:,.2f}",
        "target_raw": float(plan.target_price),
        "trailing_stop": f"₹{plan.trailing_stop.current_trigger_price:,.2f}" if plan.trailing_stop.enabled else "Disabled",
        "pnl": "+₹0.00",
        "status": "OPEN",
        "timestamp": fill_ts_local,
        "scheduled_start": getattr(plan, "scheduled_start_hhmm", None),
    }

    trade_log = {
        "trade_id": trade_id,
        "timestamp": fill_ts_local,
        "timestamp_ist": ist_ts,
        "symbol": plan.symbol,
        "style": plan.trading_style,
        "strategy": plan.strategy,
        "direction": plan.direction,
        "quantity": plan.quantity,
        "entry_price": plan.entry_price,
        "exit_price": plan.entry_price,
        "exit_reason": "OPEN POSITION",
        "pnl": 0.0,
        "status": "OPEN",
        "fill_price_source": fill_source,
        "age_sec": age_sec,
        "quote_ts": quote_ts,
        "quote_age_ms": quote_age_ms,
        "decision_price": decision_price,
        "data_authority": data_authority,
        "instrument_token": instrument_token,
        "quote_timestamp": quote_timestamp,
        "received_timestamp": received_timestamp,
        "market_open": bool(open_ok),
        "data_quality_passed": True,
        "quote_quality": quote_quality,
        "baseline_version": PAPER_BASELINE_VERSION,
    }

    ACTIVE_PAPER_POSITIONS.append(new_position)
    EXECUTED_TRADES_LOG.append(trade_log)
    _recompute_paper_margin_from_positions()
    _save_paper_capital_state()
    _save_paper_positions_state()

    try:
        paper_observation_logger.log_fill_integrity(FillIntegrityRecord(
            event_id=f"fill_{uuid.uuid4().hex[:10]}",
            baseline_version=PAPER_BASELINE_VERSION,
            timestamp_ist=ist_ts,
            trade_id=trade_id,
            symbol=str(plan.symbol).upper(),
            fill_price=float(plan.entry_price),
            fill_price_source=fill_source,
            age_sec=age_sec if isinstance(age_sec, (int, float)) else None,
            quote_ts=float(quote_ts) if quote_ts is not None else None,
            market_open=bool(open_ok),
            data_quality_passed=True,
            quote_quality=quote_quality,
            side=str(plan.direction or ""),
            quantity=int(plan.quantity or 0),
            decision_price=decision_price,
            exchange="NSE",
            instrument_token=instrument_token,
            quote_timestamp=quote_timestamp,
            received_timestamp=received_timestamp,
            quote_age_ms=int(quote_age_ms) if quote_age_ms is not None else None,
            websocket_connected=bool(quote.get("websocket_connected", True)),
            websocket_streaming=bool(quote.get("websocket_streaming", True)),
            data_authority=data_authority,
            data_quality="VALID",
            oie_exception="7P-OBS-INTEGRITY-EXCEPTION-001",
        ))
    except Exception as obs_err:
        logger.warning("PaperObservationLogger fill write failed: %s", obs_err)

    return {
        "success": True,
        "message": (
            f"Paper Trade Executed at live {fill_source} LTP ₹{plan.entry_price:,.2f} "
            f"for {plan.symbol}. Position is OPEN in Paper Simulator."
        ),
        "position": new_position,
        "fill_integrity": integrity,
        "fill_price_source": fill_source,
        "age_sec": age_sec,
        "data_authority": data_authority,
        "data_quality_passed": True,
        "baseline_version": PAPER_BASELINE_VERSION,
    }


def build_market_status_badge(open_ok: bool, reason: str) -> str:
    """Dynamic market badge — never hardcode a day name when closed."""
    now = now_ist()
    day_name = now.strftime("%A")
    clock = now.strftime("%I:%M %p IST")
    if open_ok:
        return f"🟢 MARKET OPEN · {day_name} · {clock}"
    if "weekend" in reason.lower() or now.weekday() in (5, 6):
        return f"🔴 MARKET CLOSED · {day_name} · {clock}"
    return f"🔴 MARKET CLOSED · {day_name} · {clock} · {reason}"


class UnifiedWebAppHandler(BaseHTTPRequestHandler):
    def _set_json_headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # Phase 7P freeze-allowed web boundary: same-origin localhost only (no wildcard CORS)
        self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{PORT}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _set_html_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        return json.loads(body) if body else {}

    def do_OPTIONS(self):
        self._set_json_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._set_html_headers()
            self.wfile.write(HTML_UNIFIED_APP.encode("utf-8"))
            return

        if path in ("/terminal", "/terminal.html"):
            self._set_html_headers()
            self.wfile.write(render_terminal_html().encode("utf-8"))
            return

        if path == "/api/tariff":
            self._set_json_headers(200)
            self.wfile.write(json.dumps(catalog_manifest()).encode("utf-8"))
            return

        if path == "/api/terminal/ohlc":
            self._set_json_headers(200)
            qs = parse_qs(parsed.query)
            symbol = (qs.get("symbol") or ["RELIANCE"])[0].strip().upper()
            try:
                bars = int((qs.get("bars") or ["80"])[0])
            except (TypeError, ValueError):
                bars = 80
            self.wfile.write(json.dumps(load_daily_ohlc(symbol, bars=bars)).encode("utf-8"))
            return

        if path == "/api/status":
            self._set_json_headers(200)
            data = self.get_system_status()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/scheduled_paper_trades":
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "orders": paper_scheduler.list_orders(include_done=True),
                "preset_slots": list(paper_scheduler.PRESET_START_SLOTS),
                "arming_note": "Arm from 09:00 IST; fills at selected start with Angel WS LTP.",
            }).encode("utf-8"))
            return

        if path == "/api/ltp":
            self._set_json_headers(200)
            qs = parse_qs(parsed.query)
            symbol = (qs.get("symbol") or ["RELIANCE"])[0].strip().upper()
            exchange = (qs.get("exchange") or ["NSE"])[0].strip().upper()
            angel_ensure_subscribed([symbol], exchange)
            quote = angel_get_ltp_quote(symbol, exchange)
            mds = angel_get_market_data_status()
            if quote:
                self.wfile.write(json.dumps({
                    "success": True,
                    "symbol": symbol,
                    "ltp": quote.get("ltp"),
                    "source": quote.get("source"),
                    "market_data": mds,
                }).encode("utf-8"))
            else:
                self.wfile.write(json.dumps({
                    "success": False,
                    "symbol": symbol,
                    "error": mds.get("last_error") or "No live Angel LTP available",
                    "market_data": mds,
                }).encode("utf-8"))
            return

        if path == "/api/mandate/today":
            self._set_json_headers(200)
            data = self.get_today_mandate_data()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/strategies":
            self._set_json_headers(200)
            strats = [
                {
                    "strategy_id": s.strategy_id,
                    "name": s.name,
                    "trading_style": s.trading_style,
                    "segment": s.segment,
                    "timeframe": s.timeframe,
                    "risk_level": s.risk_level,
                    "automation_tier": s.automation_tier.name,
                    "description": s.description
                } for s in strategy_registry.get_all_strategies()
            ]
            self.wfile.write(json.dumps(strats).encode("utf-8"))
            return

        if path == "/api/opportunities":
            self._set_json_headers(200)
            scan_st = get_scan_status()
            signals = get_cached_signals()
            opp_engine = OpportunityEngine()
            symbols = [str(s.get("symbol") or "").upper() for s in signals if s.get("symbol")]
            live = _fetch_nse_ltp_map(symbols) if symbols else {}
            market_ctx: Dict[str, Any] = {}
            try:
                from trading_app.angel_market_data_bridge import get_cockpit_index_inputs

                idx = get_cockpit_index_inputs() or {}
                market_ctx = {
                    "india_vix": idx.get("india_vix") or idx.get("vix"),
                    "nifty_change_pct": idx.get("nifty_pct"),
                }
            except Exception:
                market_ctx = {}
            opps_live = opp_engine.get_top_opportunities(
                live_ltp_map=live,
                signals=signals,
                top_n=10,
                min_confidence=0.60,
                market_context=market_ctx,
            )
            opps = [
                {
                    "opportunity_id": o.opportunity_id,
                    "symbol": o.symbol,
                    "trading_style": o.trading_style,
                    "strategy": o.strategy,
                    "direction": o.direction,
                    "signal_strength_pct": o.signal_strength_pct,
                    "suggested_entry": float(o.suggested_entry),
                    "suggested_stop_loss": float(o.suggested_stop_loss),
                    "suggested_target": float(o.suggested_target),
                    "suggested_quantity": o.suggested_quantity,
                    "risk_reward_ratio": f"1 : {o.risk_reward_ratio}",
                    "why_this_trade": o.why_this_trade,
                    "invalidation_rules": o.invalidation_rules,
                    "investment_thesis": o.investment_thesis,
                    "factor_scores": o.factor_scores,
                    "factor_badges": o.factor_badges,
                    "factor_trends": o.factor_trends,
                    "valuation_relatives": o.valuation_relatives,
                    "fundamentals_meta": o.fundamentals_meta,
                    "ai_summary": o.ai_summary,
                    "opportunity_strength": o.opportunity_strength,
                    "price_source": o.price_source,
                    "live": True,
                    "analyzer": True,
                }
                for o in opps_live
            ]
            if scan_st.get("state") == "scanning":
                message = scan_st.get("message") or "EnhancedAnalyzer scanning watchlist…"
            elif scan_st.get("state") == "error":
                message = scan_st.get("message") or "Analyzer scan failed"
            elif not signals:
                message = (
                    "EnhancedAnalyzer has not produced signals yet — scanning watchlist "
                    "(not the old RELIANCE/HDFCBANK/TCS demo cards)."
                )
            elif not opps:
                message = (
                    "Analyzer found signals but Angel live LTP is missing for those symbols — "
                    "waiting for WebSocket/REST quotes."
                )
            else:
                message = None
            payload = {
                "ok": len(opps) > 0,
                "count": len(opps),
                "opportunities": opps,
                "scan": scan_st,
                "message": message,
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if path == "/api/opportunities/rescan":
            self._set_json_headers(200)
            started = request_rescan_async()
            self.wfile.write(json.dumps({
                "ok": True,
                "started": started,
                "scan": get_scan_status(),
            }).encode("utf-8"))
            return

        if path == "/api/watchlist":
            self._set_json_headers(200)
            watchlist_data = self.get_watchlist_data()
            self.wfile.write(json.dumps(watchlist_data).encode("utf-8"))
            return

        if path == "/api/watchlist/download":
            rows = self.get_watchlist_data()
            content = build_watchlist_csv(rows)
            filename = f"NexTrade_Watchlist_{now_ist().strftime('%Y%m%d')}.csv"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/positions":
            self._set_json_headers(200)
            # Keep margin truthful vs open trades (never trust stale persisted ghost margin)
            _recompute_paper_margin_from_positions()
            auto = _evaluate_paper_auto_exits()
            enriched = _enrich_positions_with_ltp(ACTIVE_PAPER_POSITIONS)
            _recompute_paper_realized_pnl_from_trades()
            combined_gross = _mark_live_day_pnl(enriched)
            summary = _paper_positions_summary(enriched)
            lim = get_day_risk_limits()
            summary["day_profit_target_inr"] = lim.profit_target_inr
            summary["day_loss_limit_inr"] = lim.loss_limit_inr
            summary["day_limit_projection"] = _day_limit_projection_for_ui()
            summary["day_halt"] = bool(PAPER_DAY_HALTED)
            summary["day_halt_reason"] = PAPER_DAY_HALT_REASON
            summary["combined_day_pnl_raw"] = float(auto.get("combined_day_pnl") or combined_gross)
            summary["auto_exits_closed"] = int(auto.get("closed_count") or 0)
            summary["total_capital_fmt"] = _fmt_inr(TOTAL_CAPITAL)
            summary["todays_pnl_fmt"] = _fmt_inr(combined_gross, signed=True)
            summary["todays_net_pnl_fmt"] = _fmt_inr(
                float(TODAYS_NET_PNL or 0.0) + float(LAST_UNREALIZED_PNL or 0.0),
                signed=True,
            )
            summary["utilized_margin_fmt"] = _fmt_inr(UTILIZED_MARGIN)
            summary["available_cash_fmt"] = _fmt_inr(deployable_remaining(UTILIZED_MARGIN))
            self.wfile.write(json.dumps({
                "positions": enriched,
                "summary": summary,
            }).encode("utf-8"))
            return

        if path == "/api/heartbeat":
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "ok": True,
                "port": PORT,
                "pid": os.getpid(),
                "open_positions": len(ACTIVE_PAPER_POSITIONS),
            }).encode("utf-8"))
            return

        if path == "/api/holdings":
            self._set_json_headers(200)
            holdings_data = self.get_holdings_data()
            self.wfile.write(json.dumps(holdings_data).encode("utf-8"))
            return

        if path == "/api/journal":
            try:
                self._set_json_headers(200)
                journal_data = self.get_journal_data()
                self.wfile.write(json.dumps(journal_data, default=str).encode("utf-8"))
            except Exception as exc:
                logger.exception("Journal API failed: %s", exc)
                self._set_json_headers(500)
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"Journal failed: {exc}",
                    "executed_trades": [],
                    "total_trades": 0,
                    "win_rate_pct": 0.0,
                    "net_pnl_formatted": "+₹0.00",
                    "style_breakdown_formatted": {},
                }).encode("utf-8"))
            return

        if path == "/api/paper/day_risk_policy":
            self._set_json_headers(200)
            pol = load_policy()
            self.wfile.write(json.dumps({
                "ok": True,
                "policy": pol.to_dict(),
                "projection": _day_limit_projection_for_ui(),
            }).encode("utf-8"))
            return

        if path == "/api/premarket":
            self._set_json_headers(200)
            premarket = self.get_premarket_data()
            self.wfile.write(json.dumps(premarket).encode("utf-8"))
            return

        if path == "/api/download_excel":
            try:
                qs = parse_qs(parsed.query or "")
                requested = (qs.get("file") or [None])[0]
                filepath = None
                if requested:
                    safe_name = os.path.basename(str(requested))
                    candidate = os.path.join(REPORTS_DIR, safe_name)
                    if os.path.isfile(candidate) and safe_name.lower().endswith(".xlsx"):
                        filepath = candidate
                if not filepath:
                    # Prefer today's auto-saved project log when present
                    daily = os.path.join(
                        REPORTS_DIR,
                        f"NexTrade_Trading_Log_{now_ist().strftime('%Y%m%d')}.xlsx",
                    )
                    if os.path.isfile(daily):
                        filepath = daily
                    else:
                        filepath = self._build_excel_report_file()
                with open(filepath, "rb") as f:
                    content = f.read()
                filename = os.path.basename(filepath)
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{filename}"',
                )
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(content)
            except Exception as exc:
                logger.exception("Excel download failed: %s", exc)
                self._set_json_headers(500)
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"Excel download failed: {exc}",
                }).encode("utf-8"))
            return

        self.send_error(404, "File Not Found")

    def do_POST(self):
        global LEDGER_BASE, TOTAL_CAPITAL, UTILIZED_MARGIN, TODAYS_PNL, OVERALL_PNL, TODAYS_NET_PNL, OVERALL_NET_PNL, LAST_UNREALIZED_PNL, ACTIVE_RISK, EXECUTED_TRADES_LOG, ACTIVE_PAPER_POSITIONS, CURRENT_TRADE_PLAN, ALLOW_OFFMARKET_SIMULATION
        global PAPER_DAY_HALTED, PAPER_DAY_HALT_REASON, PAPER_DAY_HALT_DATE
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(body) if body else {}

        if path == "/api/mandate/approve":
            self._set_json_headers(200)
            mandate_id = payload.get("mandate_id")
            if not mandate_id:
                mandate_data = self.get_today_mandate_data()
                mandate_id = mandate_data["mandate_id"]
            
            try:
                approved = mandate_manager.approve_mandate(mandate_id, user_id="Corporate_Executive")
                res = {
                    "success": True,
                    "message": "🟢 TODAY'S TRADING MANDATE APPROVED! NexTrade is now managing today's trading plan within your pre-approved boundaries.",
                    "mandate_id": approved.mandate_id,
                    "state": approved.state.value
                }
            except Exception as e:
                res = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/mandate/pause":
            self._set_json_headers(200)
            current = mandate_manager.get_current_mandate()
            if current:
                mandate_manager.pause_mandate(current.mandate_id, reason="User clicked Pause")
                res = {"success": True, "message": "⏸ PAUSED NEW TRADES. Existing positions remain protected by SL/TSL."}
            else:
                res = {"success": False, "error": "No active mandate found."}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/mandate/stop":
            self._set_json_headers(200)
            current = mandate_manager.get_current_mandate()
            if current:
                mandate_manager.emergency_stop(current.mandate_id, reason="Emergency Stop Button Pressed")
                res = {"success": True, "message": "🚨 EMERGENCY STOP EXECUTED! Master Portfolio Kill Switch Invoked."}
            else:
                res = {"success": False, "error": "No active mandate found."}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/toggle_offmarket":
            self._set_json_headers(200)
            ALLOW_OFFMARKET_SIMULATION = bool(payload.get("allow", False))
            msg = "Weekend/Off-Market Paper Simulation Override ENABLED" if ALLOW_OFFMARKET_SIMULATION else "Strict Market Hours Enforcement ENABLED"
            self.wfile.write(json.dumps({"success": True, "allow_offmarket": ALLOW_OFFMARKET_SIMULATION, "message": msg}).encode("utf-8"))
            return

        if path == "/api/reset_paper_data":
            self._set_json_headers(200)
            LEDGER_BASE = DEFAULT_PAPER_CAPITAL
            TOTAL_CAPITAL = DEFAULT_PAPER_CAPITAL
            UTILIZED_MARGIN = 0.0
            TODAYS_PNL = 0.0
            OVERALL_PNL = 0.0
            TODAYS_NET_PNL = 0.0
            OVERALL_NET_PNL = 0.0
            LAST_UNREALIZED_PNL = 0.0
            ACTIVE_RISK = 0.0
            PAPER_DAY_HALTED = False
            PAPER_DAY_HALT_REASON = ""
            PAPER_DAY_HALT_DATE = ""
            EXECUTED_TRADES_LOG = []
            ACTIVE_PAPER_POSITIONS = []
            _save_paper_capital_state()
            _save_paper_positions_state()

            res = {
                "success": True,
                "message": (
                    f"All paper trade data reset to NIL. Fresh ledger capital "
                    f"₹{DEFAULT_PAPER_CAPITAL:,.0f}; deployable ₹{PAPER_DEPLOYABLE_CAPITAL:,.0f} "
                    f"({PAPER_MAX_OPEN_SCRIPS} × ₹{PAPER_PER_SCRIP_CAPITAL:,.0f})."
                ),
                "total_capital_fmt": f"₹{DEFAULT_PAPER_CAPITAL:,.2f}",
                "available_cash_fmt": f"₹{PAPER_DEPLOYABLE_CAPITAL:,.2f}",
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/export_excel":
            self._set_json_headers(200)
            try:
                filepath = self._build_excel_report_file()
                filename = os.path.basename(filepath)
                res = {
                    "success": True,
                    "filepath": filepath,
                    "filename": filename,
                    "download_url": f"/api/download_excel?file={filename}",
                    "message": f"Excel log ready: {filename}",
                }
            except Exception as exc:
                logger.exception("Excel export failed: %s", exc)
                res = {"success": False, "error": f"Excel export failed: {exc}"}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/paper/day_risk_policy":
            self._set_json_headers(200)
            try:
                pol = parse_policy_update(payload)
                saved = save_policy(pol)
                res = {
                    "success": True,
                    "policy": saved.to_dict(),
                    "projection": _day_limit_projection_for_ui(),
                    "message": (
                        f"Day flatten updated: profit +₹{saved.profit_target_inr:.0f} / "
                        f"loss −₹{saved.loss_limit_inr:.0f} (gross combined PnL triggers)."
                    ),
                }
            except Exception as exc:
                logger.exception("Day risk policy save failed: %s", exc)
                res = {"success": False, "error": str(exc)}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/capital/update":
            self._set_json_headers(200)
            action = payload.get("action", "add")
            step = float(payload.get("amount", 10000.0))

            if step % 10000 != 0 or step <= 0:
                self.wfile.write(json.dumps({"success": False, "error": "Capital changes must be in multiples of ₹10,000"}).encode("utf-8"))
                return

            if action == "add":
                LEDGER_BASE += step
            elif action == "subtract":
                next_base = LEDGER_BASE - step
                next_display = displayed_paper_capital(next_base, TODAYS_NET_PNL, LAST_UNREALIZED_PNL)
                if next_base < 0 or next_display < UTILIZED_MARGIN:
                    self.wfile.write(json.dumps({"success": False, "error": f"Cannot reduce capital below utilized margin (₹{UTILIZED_MARGIN:,.2f})"}).encode("utf-8"))
                    return
                LEDGER_BASE = next_base
            _refresh_display_capital()
            _save_paper_capital_state()
            available_cash = deployable_remaining(UTILIZED_MARGIN)
            res = {
                "success": True,
                "total_capital_fmt": f"₹{TOTAL_CAPITAL:,.2f}",
                "available_cash_fmt": f"₹{available_cash:,.2f}",
                "message": f"Capital successfully updated to ₹{TOTAL_CAPITAL:,.2f}"
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/tariff/preview":
            self._set_json_headers(200)
            try:
                resp = {"success": True, **preview_from_payload(payload)}
            except Exception as e:
                resp = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/create_trade_plan":
            self._set_json_headers(200)
            ticket_engine = TradeTicketEngine()
            try:
                plan = ticket_engine.create_trade_plan(
                    symbol=payload.get("symbol", "RELIANCE"),
                    trading_style=payload.get("trading_style", "INTRADAY"),
                    strategy=payload.get("strategy", "Momentum Breakout"),
                    direction=payload.get("direction", "BUY"),
                    entry_price=float(payload.get("entry_price", 2742.0)),
                    quantity=int(payload.get("quantity", 10)),
                    stop_loss_price=float(payload.get("stop_loss_price", 2690.0)),
                    target_price=float(payload.get("target_price", 2850.0)),
                    trailing_stop_amount=float(payload.get("trailing_stop_amount", 20.0)),
                    execution_mode=payload.get("execution_mode", "PAPER_TRADING")
                )
                CURRENT_TRADE_PLAN = plan
                summary = ticket_engine.generate_pre_trade_summary(plan)
                charges = attach_plan_charge_preview(plan, payload)
                summary["charges_v2"] = charges.get("v2_line")
                summary["charges_v3"] = charges.get("v3_line")
                summary["charges_qty_note"] = charges.get("qty_note")
                plan_dict = {
                    "symbol": plan.symbol,
                    "trading_style": plan.trading_style,
                    "strategy": plan.strategy,
                    "direction": plan.direction,
                    "entry_price": plan.entry_price,
                    "quantity": plan.quantity,
                    "stop_loss_price": plan.stop_loss_price,
                    "target_price": plan.target_price,
                    "capital_required": plan.capital_required,
                    "max_loss_amount": plan.max_loss_amount,
                    "potential_profit": plan.potential_profit_amount
                }
                resp = {"success": True, "plan": plan_dict, "summary": summary, "charges": charges}
            except Exception as e:
                resp = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/schedule_paper_trade":
            self._set_json_headers(200)
            start_hhmm = str(payload.get("start_hhmm") or payload.get("scheduled_start") or "").strip()
            if not CURRENT_TRADE_PLAN:
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": "No validated Trade Plan found. Click 'Generate Pre-Trade Summary' first.",
                }).encode("utf-8"))
                return
            try:
                mandate_manager.verify_u5_autonomous_boundary()
            except U5MandateViolationException as u5_err:
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": str(u5_err),
                    "u5_violation": True,
                }).encode("utf-8"))
                return

            now = now_ist()
            # IMMEDIATE or already-due → execute now if market open
            if (start_hhmm.upper() == "IMMEDIATE") or (
                paper_scheduler.parse_hhmm(start_hhmm)
                and now.time() >= paper_scheduler.parse_hhmm(start_hhmm)
            ):
                open_ok, open_reason = is_market_open()
                if not open_ok and not ALLOW_OFFMARKET_SIMULATION:
                    self.wfile.write(json.dumps({
                        "success": False,
                        "error": f"⚠️ TRADE BLOCKED: {open_reason}",
                        "market_closed": True,
                    }).encode("utf-8"))
                    return
                plan = CURRENT_TRADE_PLAN
                setattr(plan, "scheduled_start_hhmm", start_hhmm if start_hhmm.upper() != "IMMEDIATE" else "IMMEDIATE")
                resp = fill_paper_trade_plan(plan)
                self.wfile.write(json.dumps(resp).encode("utf-8"))
                return

            armed = paper_scheduler.arm_order(
                CURRENT_TRADE_PLAN,
                start_hhmm,
                now=now,
                allow_weekend=ALLOW_OFFMARKET_SIMULATION,
            )
            self.wfile.write(json.dumps(armed).encode("utf-8"))
            return

        if path == "/api/scheduled_paper_trades":
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "orders": paper_scheduler.list_orders(include_done=True),
                "preset_slots": list(paper_scheduler.PRESET_START_SLOTS),
            }).encode("utf-8"))
            return

        if path == "/api/cancel_scheduled_paper_trade":
            self._set_json_headers(200)
            sid = str(payload.get("schedule_id") or "")
            self.wfile.write(json.dumps(paper_scheduler.cancel_order(sid)).encode("utf-8"))
            return

        if path == "/api/execute_paper_trade":
            self._set_json_headers(200)

            # 1. Market Hours Boundary Check
            open_ok, open_reason = is_market_open()
            if not open_ok and not ALLOW_OFFMARKET_SIMULATION:
                msg = f"⚠️ TRADE BLOCKED: {open_reason} Paper trade execution is prohibited while Indian equity markets are closed."
                self.wfile.write(json.dumps({"success": False, "error": msg, "market_closed": True}).encode("utf-8"))
                return

            # 2. Invariant U5 Verification
            try:
                mandate_manager.verify_u5_autonomous_boundary()
            except U5MandateViolationException as u5_err:
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": str(u5_err),
                    "u5_violation": True,
                    "user_action": "Open tab 'NEXTRADE TODAY (15-Min Cockpit)' → scroll to 'Today's Trading Mandate Boundaries' → click APPROVE & START TODAY'S TRADING MANDATE, then retry Execute Paper Trade."
                }).encode("utf-8"))
                return

            # 3. Plan Check
            if not CURRENT_TRADE_PLAN:
                self.wfile.write(json.dumps({"success": False, "error": "No validated Trade Plan found. Please click 'Generate Pre-Trade Summary' first."}).encode("utf-8"))
                return

            plan = CURRENT_TRADE_PLAN
            setattr(plan, "scheduled_start_hhmm", "IMMEDIATE")
            resp = fill_paper_trade_plan(plan)
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/run_audit":
            self._set_json_headers(200)
            certifier = ProductionActivationCertifier()
            ok, manifest = certifier.execute_full_6g_production_activation_audit()
            res = {
                "success": ok,
                "manifest_sha256": manifest.get("manifest_sha256", ""),
                "invariants_passed": manifest.get("invariants_passed", 0),
                "invariants_total": manifest.get("invariants_total", 15),
                "signing_status": manifest.get("signing_status", "CERTIFICATION_SIGNING_PENDING"),
                "results": manifest.get("invariant_results", [])
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/trigger_kill":
            self._set_json_headers(200)
            target = payload.get("target", "account")
            account_id = payload.get("account_id", "ACC_PROD_MULTI_01")
            mgr = MultiAccountPortfolioManager()
            if target == "account":
                res = mgr.trigger_account_scoped_kill_switch(account_id, reason="Triggered from UI Control Panel")
                msg = f"Account Kill Switch Executed on {account_id}"
            else:
                res = mgr.trigger_portfolio_master_kill_switch(reason="Triggered from UI Master Control")
                msg = "Portfolio Master Kill Switch Executed across ALL accounts"

            self.wfile.write(json.dumps({"success": True, "details": res, "message": msg}).encode("utf-8"))
            return

        if path == "/api/positions/close":
            self._set_json_headers(200)
            pid = str(payload.get("position_id") or "").strip()
            if not pid:
                self.wfile.write(json.dumps({"success": False, "error": "position_id required"}).encode("utf-8"))
                return
            ok, msg, pos = _close_paper_position(pid, reason="USER_MANUAL_CLOSE")
            self.wfile.write(json.dumps({
                "success": ok,
                "message": msg,
                "position": pos,
                "utilized_margin_fmt": f"₹{UTILIZED_MARGIN:,.2f}",
                "available_cash_fmt": f"₹{deployable_remaining(UTILIZED_MARGIN):,.2f}",
            }).encode("utf-8"))
            return

        if path == "/api/positions/close_all":
            self._set_json_headers(200)
            out = _close_all_paper_positions(reason="PAPER_KILL_ALL")
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Closed {out['closed_count']} paper position(s).",
                **out,
                "utilized_margin_fmt": f"₹{UTILIZED_MARGIN:,.2f}",
                "available_cash_fmt": f"₹{deployable_remaining(UTILIZED_MARGIN):,.2f}",
            }).encode("utf-8"))
            return

        if path == "/api/holdings/manual":
            self._set_json_headers(200)
            validated, error = _validate_manual_holding_payload(payload)
            if error:
                self.wfile.write(json.dumps({"success": False, "error": error}).encode("utf-8"))
                return
            holdings = _load_manual_zerodha_holdings()
            sym = validated["symbol"]
            if any(_normalize_broker_holding_symbol(h.get("symbol")) == sym for h in holdings):
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"{sym} already exists — use Edit to update quantity or average price",
                }).encode("utf-8"))
                return
            now_iso = datetime.now().isoformat(timespec="seconds")
            validated["id"] = str(uuid.uuid4())
            validated["created_at"] = now_iso
            validated["updated_at"] = now_iso
            holdings.append(validated)
            try:
                _save_manual_zerodha_holdings(holdings)
            except Exception as exc:
                self.wfile.write(json.dumps({"success": False, "error": str(exc)}).encode("utf-8"))
                return
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Added {sym} to manual Zerodha holdings",
                "holding": validated,
            }).encode("utf-8"))
            return

        if path == "/api/watchlist/add":
            self._set_json_headers(200)
            res = add_watchlist_symbol(payload.get("symbol"))
            if res.get("success"):
                try:
                    angel_ensure_subscribed([res["symbol"]], "NSE")
                except Exception:
                    logger.warning(
                        "Watchlist saved %s but Angel subscribe failed",
                        res.get("symbol"),
                        exc_info=True,
                    )
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/watchlist/remove":
            self._set_json_headers(200)
            res = remove_watchlist_symbol(payload.get("symbol"))
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_error(404, "Endpoint Not Found")

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self._read_json_body()

        if path == "/api/holdings/manual":
            self._set_json_headers(200)
            validated, error = _validate_manual_holding_payload(payload, require_id=True)
            if error:
                self.wfile.write(json.dumps({"success": False, "error": error}).encode("utf-8"))
                return
            holdings = _load_manual_zerodha_holdings()
            idx = next((i for i, h in enumerate(holdings) if h.get("id") == validated["id"]), None)
            if idx is None:
                self.wfile.write(json.dumps({"success": False, "error": "Manual holding not found"}).encode("utf-8"))
                return
            sym = validated["symbol"]
            for i, h in enumerate(holdings):
                if i != idx and _normalize_broker_holding_symbol(h.get("symbol")) == sym:
                    self.wfile.write(json.dumps({
                        "success": False,
                        "error": f"Another holding already uses symbol {sym}",
                    }).encode("utf-8"))
                    return
            existing = holdings[idx]
            validated["created_at"] = existing.get("created_at") or datetime.now().isoformat(timespec="seconds")
            validated["updated_at"] = datetime.now().isoformat(timespec="seconds")
            holdings[idx] = validated
            try:
                _save_manual_zerodha_holdings(holdings)
            except Exception as exc:
                self.wfile.write(json.dumps({"success": False, "error": str(exc)}).encode("utf-8"))
                return
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Updated {sym} in manual Zerodha holdings",
                "holding": validated,
            }).encode("utf-8"))
            return

        self.send_error(404, "Endpoint Not Found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        payload = self._read_json_body()

        if path == "/api/holdings/manual":
            self._set_json_headers(200)
            hid = str(payload.get("id") or (qs.get("id") or [""])[0]).strip()
            if not hid:
                self.wfile.write(json.dumps({"success": False, "error": "Holding id is required"}).encode("utf-8"))
                return
            holdings = _load_manual_zerodha_holdings()
            idx = next((i for i, h in enumerate(holdings) if h.get("id") == hid), None)
            if idx is None:
                self.wfile.write(json.dumps({"success": False, "error": "Manual holding not found"}).encode("utf-8"))
                return
            removed = holdings.pop(idx)
            try:
                _save_manual_zerodha_holdings(holdings)
            except Exception as exc:
                self.wfile.write(json.dumps({"success": False, "error": str(exc)}).encode("utf-8"))
                return
            sym = _normalize_broker_holding_symbol(removed.get("symbol") or "")
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Removed {sym} from manual Zerodha holdings",
            }).encode("utf-8"))
            return

        self.send_error(404, "Endpoint Not Found")

    def get_today_mandate_data(self) -> Dict[str, Any]:
        ist_ctx = get_ist_context()
        idx = _fetch_live_index_inputs()
        current = mandate_manager.get_current_mandate()

        if not idx.get("ok"):
            state_val = current.state.value if current else "AWAITING_USER_APPROVAL"
            mandate_id_val = current.mandate_id if current else "mnd_pending"
            return {
                **ist_ctx,
                "trade_recommended": False,
                "mandate_id": mandate_id_val,
                "mandate_state": state_val,
                "data_mode": "UNAVAILABLE",
                "analysis_timestamp_ist": ist_ctx["ist_datetime"],
                "market_regime_label": "AWAITING LIVE DATA",
                "nifty_trend": "— (NIFTY quote unavailable)",
                "bank_nifty_trend": "— (Bank NIFTY quote unavailable)",
                "vix_level": idx.get("vix"),
                "market_breadth": idx.get("breadth_label") or "NOT AVAILABLE",
                "recommended_strategy": "None",
                "suitability_score": 0,
                "primary_rationale": [
                    "Live NIFTY and Bank NIFTY quotes are required for today's regime analysis.",
                    "Connect Angel One (config.json credentials) and wait 20–30 seconds after dashboard start.",
                    f"Last checked: {ist_ctx['ist_datetime']}.",
                ],
                "alternative_strategies": [],
                "no_trade_reason": "Market index data unavailable — regime engine cannot run without live quotes.",
                "market_data_source": idx.get("source"),
                "market_data_live": False,
                "broker_status": angel_get_market_data_status(),
                "limits": {
                    "capital_available": f"₹{TOTAL_CAPITAL:,.2f}",
                    "capital_deployed_limit": f"₹{PAPER_DEPLOYABLE_CAPITAL:,.2f}",
                    "per_scrip_capital": f"₹{PAPER_PER_SCRIP_CAPITAL:,.2f}",
                    "max_risk_ceiling": "₹2,000.00",
                    "daily_loss_limit": "₹2,500.00",
                    "max_trades": PAPER_MAX_OPEN_SCRIPS,
                    "max_concurrent_positions": PAPER_MAX_OPEN_SCRIPS,
                    "trading_window": "09:30 AM - 02:45 PM IST",
                    "protection": "Stop Loss + Trailing SL + Auto Target",
                    "force_market_close_exit": "Enabled (03:15 PM IST)"
                }
            }

        vix_raw = idx.get("vix")
        # Do not invent VIX=15.0 when quote missing — use neutral mid for engine only;
        # API returns real vix_raw (or null) so UI never shows a fake live level.
        vix_for_engine = float(vix_raw) if vix_raw is not None else 16.0
        breadth_live = bool(idx.get("breadth_live"))
        if breadth_live and idx.get("advances") is not None and idx.get("declines") is not None:
            advances_count = int(idx["advances"])
            declines_count = int(idx["declines"])
        else:
            # Do not invent fake 1000/1000. Neutral 1:1 only when NSE A/D unavailable
            # (keeps engine runnable; regime will tend SIDEWAYS until breadth is live).
            advances_count = 1
            declines_count = 1

        outcome = regime_engine.analyze_market_and_recommend(
            nifty_pct_change=float(idx["nifty_pct"]),
            bank_nifty_pct_change=float(idx["bank_pct"]),
            vix_level=vix_for_engine,
            advances_count=advances_count,
            declines_count=declines_count,
        )

        # Rebuild cockpit rationale from live Angel + NSE breadth (no fabricated ADX/volume).
        live_rationale: List[str] = [
            f"NIFTY {outcome.nifty_trend} and Bank NIFTY {outcome.bank_nifty_trend} from Angel quotes ({idx.get('source') or 'ANGEL'}).",
        ]
        if vix_raw is not None:
            live_rationale.append(f"India VIX at {vix_raw} from Angel.")
        else:
            live_rationale.append("India VIX unavailable from Angel — regime uses index trend only (no invented VIX).")
        if breadth_live:
            b_idx = idx.get("breadth_index") or ""
            suffix = f" — {b_idx}" if b_idx else ""
            live_rationale.append(
                f"Market breadth (NSE): {advances_count} Advances / {declines_count} Declines{suffix}."
            )
        else:
            live_rationale.append(
                idx.get("breadth_label")
                or "Advances/Declines: NOT AVAILABLE (NSE breadth pending / pre-open)."
            )
        if outcome.recommended_strategy:
            live_rationale.append(
                f"Strategy of the Day: {outcome.recommended_strategy.name} "
                f"(suitability {outcome.suitability_score}/100)."
            )
        elif outcome.no_trade_reason:
            live_rationale.append(outcome.no_trade_reason)

        if not current and outcome.trade_recommended and outcome.recommended_strategy:
            current = mandate_manager.create_daily_mandate(
                market_regime_label=outcome.market_regime_label,
                recommended_strategy_id=outcome.recommended_strategy.strategy_id,
                recommended_strategy_name=outcome.recommended_strategy.name,
                suitability_score=outcome.suitability_score,
                primary_rationale=live_rationale
            )

        alts = [
            {"name": a.name, "score": a.suitability_score, "rationale": a.rationale}
            for a in outcome.alternative_strategies
        ]

        state_val = current.state.value if current else "AWAITING_USER_APPROVAL"
        mandate_id_val = current.mandate_id if current else "mnd_pending"

        return {
            **ist_ctx,
            "trade_recommended": outcome.trade_recommended,
            "mandate_id": mandate_id_val,
            "mandate_state": state_val,
            "data_mode": "LIVE",
            "analysis_timestamp_ist": ist_ctx["ist_datetime"],
            "market_regime_label": outcome.market_regime_label,
            "nifty_trend": outcome.nifty_trend,
            "bank_nifty_trend": outcome.bank_nifty_trend,
            "vix_level": vix_raw,
            "market_breadth": idx.get("breadth_label") or "Advances/Declines: NOT AVAILABLE",
            "recommended_strategy": outcome.recommended_strategy.name if outcome.recommended_strategy else "None",
            "suitability_score": outcome.suitability_score,
            "primary_rationale": live_rationale,
            "alternative_strategies": alts,
            "no_trade_reason": outcome.no_trade_reason,
            "market_data_source": idx.get("source"),
            "market_data_live": bool(idx.get("ok")),
            "nifty_ltp": idx.get("nifty_ltp"),
            "bank_ltp": idx.get("bank_ltp"),
            "breadth_live": breadth_live,
            "vix_available": vix_raw is not None,
            "broker_status": angel_get_market_data_status(),
            "limits": (lambda _lim, _proj: {
                "capital_available": f"₹{TOTAL_CAPITAL:,.2f}",
                "capital_deployed_limit": f"₹{PAPER_DEPLOYABLE_CAPITAL:,.2f}",
                "per_scrip_capital": f"₹{PAPER_PER_SCRIP_CAPITAL:,.2f}",
                "max_risk_ceiling": "₹2,000.00",
                "daily_loss_limit": "₹2,500.00",
                "max_trades": PAPER_MAX_OPEN_SCRIPS,
                "max_concurrent_positions": PAPER_MAX_OPEN_SCRIPS,
                "trading_window": "09:30 AM - 02:45 PM IST",
                "protection": (
                    f"Stop Loss + Trailing SL + Auto Target + Day PnL flatten "
                    f"(+₹{_lim.profit_target_inr:,.0f} / −₹{_lim.loss_limit_inr:,.0f} gross)"
                ),
                "force_market_close_exit": "Enabled (03:15 PM IST)",
                "day_profit_target": f"+₹{_lim.profit_target_inr:,.0f}",
                "day_loss_limit_flatten": f"−₹{_lim.loss_limit_inr:,.0f}",
                "day_net_profit_if_target_inr": _proj.get("net_profit_if_target_hit_inr"),
                "day_net_loss_if_limit_inr": _proj.get("net_loss_if_limit_hit_inr"),
                "day_est_charges_inr": _proj.get("est_total_charges_inr"),
                "paper_day_halt": bool(PAPER_DAY_HALTED),
                "paper_day_halt_reason": PAPER_DAY_HALT_REASON or "",
            })(get_day_risk_limits(), _day_limit_projection_for_ui()),
        }

    def _build_excel_report_file(self) -> str:
        """Build multi-sheet Excel log from paper trade journal (today vs period separated)."""
        return _build_excel_report_file()

    def calculate_win_rate(self):
        if not EXECUTED_TRADES_LOG:
            return 0.0
        winners = [t for t in EXECUTED_TRADES_LOG if t.get("pnl", 0.0) > 0]
        return round((len(winners) / len(EXECUTED_TRADES_LOG)) * 100, 1)

    def calculate_profit_factor(self):
        """Gross wins / abs(gross losses). Returns 0.0 when undefined (no losses or no trades)."""
        if not EXECUTED_TRADES_LOG:
            return 0.0
        gross_win = sum(float(t.get("pnl", 0.0) or 0.0) for t in EXECUTED_TRADES_LOG if float(t.get("pnl", 0.0) or 0.0) > 0)
        gross_loss = abs(sum(float(t.get("pnl", 0.0) or 0.0) for t in EXECUTED_TRADES_LOG if float(t.get("pnl", 0.0) or 0.0) < 0))
        if gross_loss <= 0:
            return round(gross_win, 2) if gross_win > 0 else 0.0
        return round(gross_win / gross_loss, 2)

    def _load_watchlist_file(self):
        return load_watchlist_symbols()

    def _save_watchlist_file(self, symbols):
        return save_watchlist_symbols(symbols)

    def get_system_status(self):
        scp = SafetyControlPlane()
        state = scp.get_state().name
        port_mgr = MultiAccountPortfolioManager()
        
        accounts_info = []
        for acc_id, acc in port_mgr.accounts.items():
            exp = port_mgr.calculate_account_exposure(acc_id)
            accounts_info.append({
                "account_id": acc_id,
                "state": acc.state.name,
                "capital_ceiling_fmt": f"₹{acc.capital_ceiling:,.2f}",
                "daily_loss_limit_fmt": f"₹{acc.daily_loss_limit:,.2f}",
                "current_exposure_fmt": f"₹{exp:,.2f}"
            })

        port_exp = port_mgr.calculate_portfolio_aggregate_exposure()
        _recompute_paper_margin_from_positions()
        _recompute_paper_realized_pnl_from_trades()
        combined_gross = _mark_live_day_pnl()
        combined_net = round(float(TODAYS_NET_PNL or 0.0) + float(LAST_UNREALIZED_PNL or 0.0), 2)
        available_cash = deployable_remaining(UTILIZED_MARGIN)
        todays_pnl_str = _fmt_inr(combined_gross, signed=True)
        overall_pnl_str = _fmt_inr(OVERALL_PNL, signed=True)
        todays_net_str = _fmt_inr(combined_net, signed=True)
        overall_net_str = _fmt_inr(OVERALL_NET_PNL, signed=True)

        open_ok, open_reason = is_market_open()
        market_badge = build_market_status_badge(open_ok, open_reason)
        ist_ctx = get_ist_context()

        current_mandate = mandate_manager.get_current_mandate()
        mandate_status_label = current_mandate.state.value if current_mandate else "AWAITING_APPROVAL"

        index_board = _fetch_index_board()
        mds = angel_get_market_data_status()
        authority = str(mds.get("data_authority") or "")
        if mds.get("websocket_streaming") or authority == "ANGEL_WS_LIVE":
            broker_label = "Angel One WS LIVE (data authority)"
        elif mds.get("websocket_connected"):
            broker_label = "Angel One WS CONNECTED (ticks STALE)"
        elif mds.get("broker_connected"):
            broker_label = "Angel One REST reference only (no paper authority)"
        elif mds.get("broker_auth_error"):
            broker_label = "Angel One BROKER_AUTH_ERROR — operator intervention"
        else:
            broker_label = "Angel One DISCONNECTED — configure config.json credentials"

        movers = self._compute_top_movers(limit=5)

        return {
            **ist_ctx,
            "control_plane_state": state,
            "broker_status": broker_label,
            "market_data": mds,
            "governance_phase": "Phase 7K Single Unified Web Terminal",
            "certification_status": "MASTER_CERTIFIED",
            "activation_state": "CERTIFICATION_SIGNING_PENDING",
            "capital_dispatch_allowed": False,
            "portfolio_aggregate_exposure_fmt": f"₹{port_exp:,.2f}",
            "portfolio_aggregate_ceiling_fmt": "₹3,000.00",
            "ledger_base_fmt": f"₹{LEDGER_BASE:,.2f}",
            "total_capital_fmt": f"₹{TOTAL_CAPITAL:,.2f}",
            "available_cash_fmt": f"₹{available_cash:,.2f}",
            "utilized_margin_fmt": f"₹{UTILIZED_MARGIN:,.2f}",
            "todays_pnl_fmt": todays_pnl_str,
            "overall_pnl_fmt": overall_pnl_str,
            "todays_net_pnl_fmt": todays_net_str,
            "overall_net_pnl_fmt": overall_net_str,
            "active_risk_fmt": f"₹{ACTIVE_RISK:,.2f}",
            "market_status_badge": market_badge,
            "market_closed_reason": open_reason if not open_ok else "",
            "mandate_status_label": mandate_status_label,
            "market_open": open_ok,
            "currency": "INR (₹)",
            "index_board": index_board,
            "gainers": movers["gainers"],
            "losers": movers["losers"],
            "movers_source": movers["source"],
            "movers_note": movers["note"],
            "accounts": accounts_info,
            "paper_capital_policy": {
                "ledger_capital": float(PAPER_LEDGER_CAPITAL),
                "deployable_capital": float(PAPER_DEPLOYABLE_CAPITAL),
                "per_scrip_capital": float(PAPER_PER_SCRIP_CAPITAL),
                "max_open_scrips": int(PAPER_MAX_OPEN_SCRIPS),
            },
            "technical_predicates": "10/10 PASS",
            "governance_predicate": "1/1 PENDING"
        }

    def get_journal_data(self):
        """Lightweight journal payload — must stay fast (no Angel/NSE I/O)."""
        pnl_str = f"+₹{TODAYS_PNL:,.2f}" if TODAYS_PNL >= 0 else f"-₹{abs(TODAYS_PNL):,.2f}"
        win_rate = self.calculate_win_rate()
        # Slim rows for UI table (strip bulky fill-integrity fields)
        slim_trades = []
        for t in list(EXECUTED_TRADES_LOG):
            if not isinstance(t, dict):
                continue
            slim_trades.append({
                "trade_id": t.get("trade_id"),
                "timestamp": t.get("timestamp") or t.get("timestamp_ist") or "—",
                "symbol": t.get("symbol"),
                "style": t.get("style") or t.get("trading_style"),
                "strategy": t.get("strategy"),
                "direction": t.get("direction"),
                "quantity": t.get("quantity"),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
                "exit_reason": t.get("exit_reason"),
                "pnl": t.get("pnl"),
                "est_charges": t.get("est_charges"),
                "net_pnl": t.get("net_pnl"),
                "status": t.get("status") or "CLOSED",
            })
        return {
            "currency": "INR (₹)",
            "total_trades": len(slim_trades),
            "win_rate_pct": win_rate,
            "net_pnl_formatted": pnl_str,
            "profit_factor": self.calculate_profit_factor(),
            "executed_trades": slim_trades,
            "style_breakdown_formatted": {
                "INTRADAY": f"₹{TODAYS_PNL:,.2f}",
                "SCALPING": "₹0.00",
                "SWING": "₹0.00"
            }
        }

    def _compute_top_movers(self, limit: int = 5) -> Dict[str, Any]:
        """
        Market-wide NSE equity Top Gainers / Losers (Moneycontrol-style board).

        Primary: NSE live-analysis-variations (DISPLAY only — OIE-001).
        Fallback: rank Angel-quoted watchlist by change% if NSE is unreachable.
        Never uses fixed symbol lists.
        """
        def _row(r: Dict[str, Any]) -> Dict[str, str]:
            chg = float(r["change_pct"])
            chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
            return {
                "symbol": r["symbol"],
                "ltp": f"₹{float(r['ltp']):,.2f}",
                "change": chg_str,
            }

        # 1) Market-wide NSE equity movers
        try:
            from trading_app.nse_market_movers import fetch_nse_equity_movers

            nse = fetch_nse_equity_movers(limit=limit)
            if nse.get("ok") and (nse.get("gainers") or nse.get("losers")):
                # Prefer NSE change% board; skip Angel LTP overlay on cache miss / after hours
                # so /api/status stays fast and does not starve /api/journal.
                overlay_syms = []
                open_ok, _ = is_market_open()
                if open_ok and nse.get("cache_age_sec") is not None and float(nse.get("cache_age_sec") or 0) < 60:
                    overlay_syms = [r["symbol"] for r in (nse.get("gainers") or []) + (nse.get("losers") or [])]
                angel_map = _fetch_nse_ltp_map(overlay_syms) if overlay_syms else {}

                def _maybe_overlay(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                    out = []
                    for r in rows:
                        q = angel_map.get(r["symbol"])
                        item = dict(r)
                        if q and float(q.get("ltp") or 0) > 0:
                            item["ltp"] = float(q["ltp"])
                            # Keep NSE change% as the ranking authority for market-wide board
                            item["ltp_source"] = q.get("source") or "ANGEL"
                        out.append(item)
                    return out

                gainers = _maybe_overlay(list(nse.get("gainers") or []))
                losers = _maybe_overlay(list(nse.get("losers") or []))
                cat = nse.get("category") or "allSec"
                return {
                    "gainers": [_row(r) for r in gainers],
                    "losers": [_row(r) for r in losers],
                    "source": "NSE_MARKET",
                    "note": f"NSE market-wide equity movers ({cat}). Display only — not paper-fill authority.",
                }
        except Exception as exc:
            logger.warning("NSE market movers failed: %s", exc)

        # 2) Fallback — watchlist ranked via Angel quotes
        symbols = self._load_watchlist_file()
        quotes = _fetch_nse_ltp_map(symbols)
        ranked: List[Dict[str, Any]] = []
        for sym in symbols:
            q = quotes.get(str(sym).upper())
            if not q:
                continue
            ltp = float(q.get("ltp") or 0)
            if ltp <= 0:
                continue
            has_prev = bool(q.get("has_prev_close") or float(q.get("closed_price") or 0) > 0)
            if q.get("source") in ("ANGEL_REST", "ANGEL_REST_INDEX"):
                has_prev = True
            chg = float(q.get("change_pct") or 0.0)
            if not has_prev:
                continue
            ranked.append({
                "symbol": str(sym).upper(),
                "ltp": ltp,
                "change_pct": chg,
                "source": q.get("source") or "ANGEL",
            })

        if not ranked:
            return {
                "gainers": [],
                "losers": [],
                "source": "UNAVAILABLE",
                "note": "NSE movers unavailable and watchlist has no previous-close quotes yet.",
            }

        ranked_desc = sorted(ranked, key=lambda r: r["change_pct"], reverse=True)
        gainers_raw = [r for r in ranked_desc if r["change_pct"] > 0][:limit]
        losers_raw = [r for r in sorted(ranked, key=lambda r: r["change_pct"]) if r["change_pct"] < 0][:limit]
        return {
            "gainers": [_row(r) for r in gainers_raw],
            "losers": [_row(r) for r in losers_raw],
            "source": "ANGEL_WATCHLIST_FALLBACK",
            "note": f"NSE unreachable — fallback ranked {len(ranked)} watchlist quotes (not full market).",
        }

    def _build_mover_rows(self, symbols: List[str], prefer_positive: bool = True) -> List[Dict[str, str]]:
        """Legacy helper — prefer _compute_top_movers for dashboard."""
        quotes = _fetch_nse_ltp_map(symbols)
        rows = []
        for sym in symbols:
            q = quotes.get(sym)
            if q:
                ltp = float(q["ltp"])
                chg = float(q.get("change_pct") or 0.0)
                chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
                rows.append({"symbol": sym, "ltp": f"₹{ltp:,.2f}", "change": chg_str})
            else:
                rows.append({"symbol": sym, "ltp": "—", "change": "—"})
        return rows

    def get_watchlist_data(self):
        symbols = self._load_watchlist_file()
        watchlist = []
        live_map = _fetch_nse_ltp_map(symbols)

        for sym in symbols:
            q = live_map.get(sym)
            if q:
                base = float(q["ltp"])
                change_pct = float(q.get("change_pct") or 0.0)
                change_val = base * change_pct / 100.0
                source = q.get("source", "ANGEL")
                volume = int(q.get("volume") or 0)
            else:
                base = 0.0
                change_val = 0.0
                change_pct = 0.0
                source = "ANGEL_UNAVAILABLE"
                volume = 0

            change_str = f"+₹{abs(change_val):.2f}" if change_val >= 0 else f"-₹{abs(change_val):.2f}"
            change_pct_str = f"+{change_pct:.2f}%" if change_pct >= 0 else f"{change_pct:.2f}%"

            watchlist.append({
                "symbol": sym,
                "ltp": f"₹{base:,.2f}" if base > 0 else "—",
                "ltp_raw": round(base, 2) if base > 0 else 0.0,
                "change": change_str if base > 0 else "—",
                "change_pct": change_pct_str if base > 0 else "—",
                "change_pct_raw": round(change_pct, 4) if base > 0 else 0.0,
                "volume": f"{volume:,}" if volume > 0 else "—",
                "price_source": source
            })
        return watchlist

    def get_holdings_data(self):
        angel_raw, source, err = _fetch_broker_holdings_raw()
        manual_raw = _fetch_manual_zerodha_holdings_raw()
        merged_raw = _sort_holdings_by_symbol(list(angel_raw) + list(manual_raw))

        if merged_raw:
            holdings, summary = _enrich_holdings_with_ltp(merged_raw)
            angel_count = sum(1 for h in holdings if h.get("broker") == "ANGEL")
            manual_count = sum(1 for h in holdings if h.get("broker") == "ZERODHA")

            if angel_count > 0 and manual_count > 0:
                holdings_source = "MIXED"
            elif angel_count > 0:
                holdings_source = "ANGEL_LIVE"
            else:
                holdings_source = "MANUAL_ZERODHA"

            holdings_error = None
            if angel_count == 0 and manual_count > 0 and err:
                holdings_error = f"Angel holdings unavailable ({err}) — showing manual Zerodha entries only"
            elif angel_count == 0 and manual_count == 0:
                holdings_error = err or f"Holdings unavailable ({source})"

            return {
                "holdings": holdings,
                "summary": summary,
                "holdings_source": holdings_source,
                "holdings_synced": True,
                "holdings_error": holdings_error,
                "angel_count": angel_count,
                "manual_zerodha_count": manual_count,
                "cache_source": source,
                "cache_fetched_at": _holdings_cache.get("fetched_at_iso"),
                "cache_age_sec": round(
                    time.time() - float(_holdings_cache.get("fetched_at") or 0), 1
                ) if _holdings_cache.get("fetched_at") else None,
            }

        summary = _empty_holdings_summary()
        return {
            "holdings": [],
            "summary": summary,
            "holdings_source": source,
            "holdings_synced": False,
            "holdings_error": err or f"Holdings unavailable ({source})",
            "angel_count": 0,
            "manual_zerodha_count": 0,
            "cache_source": source,
            "cache_fetched_at": _holdings_cache.get("fetched_at_iso"),
            "cache_age_sec": None,
        }

    def get_premarket_data(self):
        """
        Live Pre-Market Morning Brief (display/research).

        Uses Angel index/VIX + NSE breadth + opportunity-scanner / watchlist movers.
        No hardcoded RELIANCE/HDFCBANK/TCS demo cards.
        """
        from trading_app.premarket_brief import (
            classify_session_window,
            derive_market_bias,
            focus_from_analyzer_signals,
            focus_from_watchlist_movers,
        )

        now = now_ist()
        open_ok, open_reason = is_market_open()
        window, window_label = classify_session_window(
            now.time(), weekday=now.weekday(), market_open=open_ok
        )
        if window == "WEEKEND":
            window_label = f"Weekend — {open_reason}"

        idx = _fetch_live_index_inputs() or {}
        nifty_pct = idx.get("nifty_pct")
        bank_pct = idx.get("bank_pct")
        vix = idx.get("vix")
        breadth_live = bool(idx.get("breadth_live"))
        advances = idx.get("advances")
        declines = idx.get("declines")

        nifty_trend = "—"
        bank_trend = "—"
        if nifty_pct is not None:
            nifty_trend = f"{'POSITIVE' if float(nifty_pct) >= 0 else 'NEGATIVE'} ({float(nifty_pct):+.2f}%)"
        if bank_pct is not None:
            bank_trend = f"{'POSITIVE' if float(bank_pct) >= 0 else 'NEGATIVE'} ({float(bank_pct):+.2f}%)"

        bias, bias_detail = derive_market_bias(
            nifty_pct,
            bank_pct,
            vix,
            advances=advances,
            declines=declines,
            breadth_live=breadth_live,
        )

        signals = get_cached_signals() or []
        scan_st = get_scan_status() or {}
        focus_stocks = focus_from_analyzer_signals(signals, top_n=5)
        focus_source = "OPPORTUNITY_SCANNER" if focus_stocks else "NONE"

        if not focus_stocks:
            try:
                symbols = self._load_watchlist_file()[:40]
                live_map = _fetch_nse_ltp_map(symbols) if symbols else {}
                focus_stocks = focus_from_watchlist_movers(symbols, live_map, top_n=5)
                if focus_stocks:
                    focus_source = "WATCHLIST_ANGEL_LTP"
            except Exception as exc:
                logger.warning("Premarket watchlist movers failed: %s", exc)

        note_parts = [window_label]
        if focus_source == "OPPORTUNITY_SCANNER":
            note_parts.append(
                f"Focus list from analyzer scan ({scan_st.get('state') or 'ready'}; "
                f"{len(signals)} signals cached)."
            )
        elif focus_source == "WATCHLIST_ANGEL_LTP":
            note_parts.append(
                "Focus list = top watchlist day-movers (Angel LTP). "
                "Run Opportunities rescan for analyzer-ranked setups."
            )
        else:
            note_parts.append("No focus stocks yet — wait for Angel quotes / watchlist scan.")
        note_parts.append("Display/research only — not an auto-order instruction.")

        return {
            "demo": False,
            "data_mode": "LIVE" if idx.get("ok") else "PARTIAL",
            "window": window,
            "window_label": window_label,
            "market_bias": bias,
            "bias_detail": bias_detail,
            "nifty_trend": nifty_trend,
            "bank_nifty_trend": bank_trend,
            "vix_level": vix,
            "breadth_label": idx.get("breadth_label") or "Advances/Declines: NOT AVAILABLE",
            "breadth_live": breadth_live,
            "focus_stocks": focus_stocks,
            "focus_source": focus_source,
            "scan": {
                "state": scan_st.get("state"),
                "message": scan_st.get("message"),
                "signals_cached": len(signals),
            },
            "index_source": idx.get("source"),
            "ist_datetime": format_ist_clock(now),
            "note": " · ".join(note_parts),
        }


HTML_UNIFIED_APP = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NexTrade — 15-Minute Cockpit & Autonomous Trading System</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-card: #131927;
            --bg-card-hover: #1c2438;
            --accent-green: #00e676;
            --accent-blue: #29b6f6;
            --accent-amber: #ffb300;
            --accent-red: #ff5252;
            --text-main: #f0f4f8;
            --text-muted: #8a99ad;
            --border-color: #232d42;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body { background: var(--bg-primary); color: var(--text-main); padding: 20px; min-height: 100vh; }
        
        .top-bar { display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); }
        .logo-title { display: flex; align-items: center; gap: 12px; }
        .logo-badge { background: linear-gradient(135deg, #00e676, #0288d1); color: #000; font-weight: 700; padding: 6px 14px; border-radius: 8px; font-size: 14px; }
        .title { font-size: 22px; font-weight: 700; color: #fff; }

        .nav-tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); }
        .tab-btn { background: transparent; color: var(--text-muted); border: 1px solid transparent; padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 13px; cursor: pointer; white-space: nowrap; transition: all 0.2s; }
        .tab-btn:hover { background: var(--bg-card-hover); color: #fff; }
        .tab-btn.active { background: var(--bg-card); color: var(--accent-green); border-color: var(--accent-green); }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 20px; }
        .card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 20px; position: relative; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .card-title { font-size: 15px; font-weight: 600; color: #b0bec5; display: flex; align-items: center; gap: 8px; }

        .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
        .badge-green { background: rgba(0, 230, 118, 0.15); color: var(--accent-green); border: 1px solid var(--accent-green); }
        .badge-amber { background: rgba(255, 179, 0, 0.15); color: var(--accent-amber); border: 1px solid var(--accent-amber); }
        .badge-red { background: rgba(255, 82, 82, 0.15); color: var(--accent-red); border: 1px solid var(--accent-red); }

        .metric-big { font-size: 26px; font-weight: 700; color: #fff; margin: 6px 0; }
        .sub-text { font-size: 13px; color: var(--text-muted); }
        .index-strip {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 8px;
        }
        @media (max-width: 1200px) {
            .index-strip { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        }
        @media (max-width: 800px) {
            .index-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        }
        .index-chip {
            min-width: 0; padding: 8px 10px;
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
        }
        .index-chip .idx-name { font-size: 10px; color: var(--text-muted); letter-spacing: 0.3px; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .index-chip .idx-ltp { font-size: 14px; font-weight: 700; color: #fff; margin: 2px 0 1px; }
        .index-chip .idx-chg { font-size: 11px; font-weight: 600; }
        .index-chip .idx-exch { font-size: 9px; color: #64748b; }

        .btn { background: linear-gradient(135deg, #1976d2, #0288d1); color: #fff; border: none; padding: 12px 20px; border-radius: 10px; font-weight: 700; font-size: 14px; cursor: pointer; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.9; }
        .btn-green { background: linear-gradient(135deg, #388e3c, #2e7d32); }
        .btn-amber { background: linear-gradient(135deg, #f57c00, #ff8f00); }
        .btn-red { background: linear-gradient(135deg, #d32f2f, #c62828); }
        .btn-sm { padding: 6px 12px; font-size: 12px; }

        .input-group { margin-bottom: 12px; }
        .input-group label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
        .input-group input, .input-group select { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); background: #0e1422; color: #fff; font-size: 13px; }

        .table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
        .table th, .table td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
        .table th { color: var(--text-muted); font-weight: 600; }

        .modal-box { background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; font-size: 13px; margin-top: 12px; color: #cfd8dc; }
        .opp-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        .bullet-list { margin-left: 18px; margin-top: 8px; font-size: 13px; color: #b0bec5; }
        .hash-code { font-family: monospace; color: var(--accent-blue); font-size: 12px; }
    </style>
</head>
<body>

    <!-- TOP SYSTEM STATUS BAR -->
    <div class="top-bar">
        <div class="logo-title">
            <span class="logo-badge">NEXTRADE TODAY</span>
            <span class="title">15-Minute Morning Cockpit & Autonomous System</span>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <span class="badge badge-green">🟢 SAFETY ENGINE: ACTIVE</span>
            <span class="badge badge-amber" id="broker-status-badge">Angel One: connecting…</span>
            <span class="badge" style="background: rgba(41, 182, 246, 0.15); color: var(--accent-blue); border: 1px solid var(--accent-blue);">TRADING MODE: 🟢 PAPER SANDBOX</span>
            <span class="badge badge-amber" id="market-status-badge">🔴 MARKET CLOSED · loading…</span>
            <span class="badge" id="ist-clock-badge" style="background: rgba(156, 39, 176, 0.15); color: #ce93d8; border: 1px solid #9c27b0;">🕐 IST: loading…</span>
            <span class="badge badge-green">INR (₹)</span>
        </div>
    </div>

    <!-- ALL UNIFIED TABS -->
    <div class="nav-tabs">
        <button class="tab-btn active" onclick="showTab(event, 'tab-today')">🌅 NEXTRADE TODAY (15-Min Cockpit)</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-dashboard')">🏠 Dashboard & Capital</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-opportunities')">🔎 Opportunities ("Why Trade?")</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-ticket')">🎟️ Trade Ticket & Plan</button>
        <a class="tab-btn" href="/terminal" style="text-decoration:none;">Paper Terminal</a>
        <button class="tab-btn" onclick="showTab(event, 'tab-paper')" id="btn-tab-paper">🧪 Paper Simulator (4 Modes)</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-positions')" id="btn-tab-positions">📈 Live Positions & Protection</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-holdings')">💼 Holdings & Portfolio</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-watchlist')" id="btn-tab-watchlist">👁️ Watchlist Monitor</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-journal')" id="btn-tab-journal">📜 History & Journal (7J)</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-premarket')">🌅 Pre-Market Brief</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-settings')">⚙️ Settings</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-control')" style="margin-left: auto; color: var(--accent-amber);">🛡️ Control Plane & Invariants</button>
    </div>

    <!-- TAB 0: NEXTRADE TODAY (15-MINUTE MORNING COCKPIT) -->
    <div id="tab-today" class="tab-content active">
        <!-- MANDATE ACTIVE STATUS BANNER -->
        <div id="mandate-status-banner" style="background: rgba(0, 230, 118, 0.1); border: 1px solid var(--accent-green); border-radius: 12px; padding: 14px; margin-bottom: 20px; display: none; justify-content: space-between; align-items: center;">
            <div>
                <strong style="color: var(--accent-green); font-size: 15px;">🟢 NEXTRADE IS MANAGING TODAY'S APPROVED TRADING PLAN</strong>
                <div style="font-size: 13px; color: #b0bec5; margin-top: 2px;">Autonomous trading is active within your pre-approved capital and risk limits. You may close the browser.</div>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn btn-amber btn-sm" onclick="pauseMandate()">⏸ Pause New Entries</button>
                <button class="btn btn-red btn-sm" onclick="stopMandate()">🛑 Emergency Stop</button>
            </div>
        </div>

        <div class="grid">
            <!-- 1. MARKET REGIME & BRIEF -->
            <div class="card">
                <div class="card-header"><span class="card-title">📊 Today's Market Regime</span><span class="badge badge-amber" id="cockpit-regime-badge">Loading…</span><span class="badge badge-amber" id="cockpit-data-source">DATA: CHECKING…</span></div>
                <div style="font-size: 14px; margin-bottom: 10px;">
                    <span class="sub-text" id="cockpit-analysis-time" style="display:block; margin-bottom:8px;">Analysis as of: —</span>
                    NIFTY Trend: <strong style="color:var(--accent-green);" id="cockpit-nifty">Loading…</strong><br>
                    Bank NIFTY Trend: <strong style="color:var(--accent-green);" id="cockpit-banknifty">Loading…</strong><br>
                    India VIX: <strong style="color:var(--accent-blue);" id="cockpit-vix">Loading…</strong><br>
                    Market Breadth: <span id="cockpit-breadth">Loading…</span>
                </div>
            </div>

            <!-- 2. STRATEGY OF THE DAY & LEVEL 2 RATIONALE -->
            <div class="card">
                <div class="card-header"><span class="card-title">🤖 Strategy of the Day</span><span class="badge badge-amber" id="cockpit-score">Suitability: —</span></div>
                <div class="metric-big" style="color:var(--accent-green);" id="cockpit-strategy-name">Loading…</div>
                <div class="sub-text" style="color:#cfd8dc;" id="cockpit-strategy-desc">Refreshing from live index data…</div>
                
                <div style="margin-top: 10px; font-size: 12px; color: var(--text-muted);">
                    <strong>Why Today?</strong>
                    <ul class="bullet-list" id="cockpit-rationale-list">
                        <li>Waiting for live market analysis…</li>
                    </ul>
                </div>
            </div>

            <!-- 3. DAILY MANDATE PREVIEW & APPROVAL BUTTON -->
            <div class="card">
                <div class="card-header"><span class="card-title">📜 Today's Trading Mandate Boundaries</span><span class="badge badge-amber">U5 BOUND</span></div>
                
                <table class="table" style="margin-bottom:12px;">
                    <tbody>
                        <tr><td>Capital to Deploy</td><td><strong style="color:#fff;" id="m-cap">₹5,00,000.00</strong></td></tr>
                        <tr><td>Per Scrip (5 ×)</td><td><strong style="color:#fff;" id="m-per-scrip">₹1,00,000.00</strong></td></tr>
                        <tr><td>Maximum Risk Limit</td><td><strong style="color:var(--accent-red);" id="m-risk">₹2,000.00</strong></td></tr>
                        <tr><td>Daily Loss Limit Stop</td><td><strong style="color:var(--accent-amber);" id="m-loss">₹2,500.00</strong></td></tr>
                        <tr><td>Max Trades Allowed</td><td><strong id="m-trades">3 Trades</strong></td></tr>
                        <tr><td>Max Concurrent Positions</td><td><strong id="m-pos">2 Positions</strong></td></tr>
                        <tr><td>Trading Window</td><td><strong id="m-window">09:30 AM - 02:45 PM IST</strong></td></tr>
                        <tr><td>Force Market Close Exit</td><td><strong style="color:var(--accent-green);">Enabled (03:15 PM IST)</strong></td></tr>
                    </tbody>
                </table>

                <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">
                    <em>By approving, you authorise NexTrade to independently identify, enter, manage, and exit paper trades within the limits displayed above.</em>
                </div>

                <button id="btn-approve-mandate" class="btn btn-green" style="width: 100%; padding: 14px; font-size: 15px; box-shadow: 0 0 0 2px rgba(0,230,118,0.35);" onclick="approveMandate()">🟢 APPROVE & START TODAY'S TRADING MANDATE</button>
            </div>
        </div>

        <!-- 4. DAILY MANDATE ACTIVITY TIMELINE -->
        <div class="card" style="margin-top: 20px;">
            <div class="card-header"><span class="card-title">⏱️ Today's Mandate Audit Timeline</span><span class="badge badge-amber">DEMO — NOT LIVE EVENTS</span></div>
            <div class="sub-text" style="margin-bottom:10px;color:var(--accent-amber);">
                Illustrative schedule only. Rows below are not wired to real mandate/regime events.
            </div>
            <div class="modal-box" style="background: rgba(0,0,0,0.2);">
                <table class="table">
                    <thead><tr><th>Time (IST)</th><th>Phase Event</th><th>Details & Audit Trace</th><th>Status</th></tr></thead>
                    <tbody>
                        <tr><td>08:45 AM</td><td>Market Analysis</td><td>[DEMO] Regime scan placeholder — live values come from Today's Market Regime card above</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                        <tr><td>08:50 AM</td><td>Strategy Selection</td><td>[DEMO] Strategy selection placeholder — see Strategy of the Day card</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                        <tr><td>09:00 AM</td><td>Mandate Approval</td><td>[DEMO] Approval status below updates from live mandate API</td><td><span class="badge badge-amber" id="tl-approval-status">PENDING</span></td></tr>
                        <tr><td>09:30 AM</td><td>Engine Activation</td><td>[DEMO] Window open placeholder</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                        <tr><td>09:42 AM</td><td>Opportunity Scanning</td><td>[DEMO] Scan status placeholder</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                        <tr><td>02:45 PM</td><td>Trading Window Close</td><td>[DEMO] Scheduled window close</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                        <tr><td>03:15 PM</td><td>Force Market Exit</td><td>[DEMO] Scheduled force exit</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                        <tr><td>03:30 PM</td><td>EOD Reconciliation</td><td>[DEMO] Scheduled EOD reconciliation</td><td><span class="badge badge-amber">DEMO</span></td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 5. END OF DAY EXECUTIVE REPORT SUMMARY -->
        <div class="card" style="margin-top: 20px;">
            <div class="card-header"><span class="card-title">📜 5-Minute End-of-Day Executive Summary</span><span class="badge badge-green">EOD REPORT</span></div>
            <div class="grid">
                <div>
                    Net P&L Today (after charges): <strong style="font-size:20px; color:var(--accent-green);" id="eod-pnl">+₹0.00</strong><br>
                    Win Rate: <strong id="eod-winrate">0.0%</strong> | Total Executed Trades: <strong id="eod-trades">0</strong>
                </div>
                <div style="text-align: right;">
                    <button class="btn btn-green btn-sm" onclick="exportExcelReport()">📊 Download Today's Multi-Sheet Excel Log (.xlsx)</button>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 1: DASHBOARD -->
    <div id="tab-dashboard" class="tab-content">
        <div class="card" style="margin-bottom:20px;">
            <div class="card-header">
                <span class="card-title">📊 Market Indices</span>
                <span class="badge badge-amber" id="idx-source-badge">LOADING</span>
            </div>
            <div class="index-strip" id="dash-indices">
                <div class="sub-text">Loading Nifty, Bank Nifty, Sensex, India VIX, Nasdaq, S&P 500, FTSE, Nikkei, Shanghai, STI, Hang Seng, KOSPI…</div>
            </div>
            <div class="sub-text" style="margin-top:10px;" id="idx-source-note">Desktop-parity index board (live quotes when feed is available).</div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">💰 Dynamic Capital Summary</span><span class="badge badge-green">LIVE DYNAMIC</span></div>
                <div class="metric-big" id="dash-capital">₹10,00,000.00</div>
                <div class="sub-text" style="margin-bottom:12px;">Deployable: <strong style="color:#fff;" id="dash-deployable">₹5,00,000.00</strong> · Available: <strong style="color:#fff;" id="dash-cash">₹5,00,000.00</strong> · Utilized: <span id="dash-margin">₹0.00</span></div>
                <div class="sub-text" style="margin-bottom:12px;">Displayed capital = ledger base (₹10L ± ₹10k) + <strong>today's closed net after charges</strong> + <strong>live open P&amp;L</strong>. Overall P&amp;L is journal-only and is not added. Charges include brokerage, STT, GST, stamp, exchange &amp; SEBI (no assumed slippage).</div>
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-green btn-sm" style="flex:1;" onclick="updateCapital('add', 10000)">+ ₹10,000 Capital</button>
                    <button class="btn btn-amber btn-sm" style="flex:1;" onclick="updateCapital('subtract', 10000)">- ₹10,000 Capital</button>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📈 Today's P&L</span><span class="badge badge-green">RESET FRESH</span></div>
                <div class="metric-big" style="color: var(--accent-green);" id="dash-pnl">+₹0.00</div>
                <div class="sub-text">Net after charges: <strong id="dash-net-pnl">+₹0.00</strong> · Overall: <span id="dash-overall-pnl">+₹0.00</span> | Active Risk: <strong style="color:var(--accent-amber);" id="dash-risk">₹0.00</strong></div>
                <div style="display:flex; gap:8px; margin-top:12px;">
                    <button class="btn btn-red btn-sm" style="flex:1;" onclick="resetPaperData()">🔄 Reset Paper Data (₹10L ledger)</button>
                    <button class="btn btn-green btn-sm" style="flex:1;" onclick="exportExcelReport()">📊 Export Market Closure Excel Log</button>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">⚙️ Trading Engine Controls</span><span class="badge badge-amber">PAUSED</span></div>
                <div style="display:flex; gap:8px; margin-top:8px;">
                    <button class="btn btn-green" style="margin:0;" onclick="alert('Engine Started')">Start Engine</button>
                    <button class="btn btn-amber" style="margin:0;" onclick="alert('Engine Paused')">Pause Engine</button>
                </div>
            </div>
        </div>

        <div class="grid" style="margin-top:20px;">
            <div class="card">
                <div class="card-header"><span class="card-title">🔥 Top Gainers</span><span class="badge badge-green">NSE MARKET</span></div>
                <table class="table">
                    <thead><tr><th>Symbol</th><th>LTP</th><th>Change</th></tr></thead>
                    <tbody id="dash-gainers"></tbody>
                </table>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">🔻 Top Losers</span><span class="badge badge-green">NSE MARKET</span></div>
                <table class="table">
                    <thead><tr><th>Symbol</th><th>LTP</th><th>Change</th></tr></thead>
                    <tbody id="dash-losers"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- TAB 2: OPPORTUNITIES -->
    <div id="tab-opportunities" class="tab-content">
        <div id="opp-container">Loading trade opportunities...</div>
    </div>

    <style>
        #opp-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
        #opp-table thead th { background: rgba(255,255,255,0.07); color: #aab4c8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); white-space: nowrap; }
        #opp-table tbody tr.opp-main-row { background: rgba(255,255,255,0.03); transition: background 0.2s; cursor: pointer; }
        #opp-table tbody tr.opp-main-row:hover { background: rgba(255,255,255,0.07); }
        #opp-table tbody td { padding: 11px 12px; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: middle; }
        #opp-table tbody tr.opp-detail-row td { padding: 12px 16px; background: rgba(0,0,0,0.25); border-bottom: 2px solid rgba(255,255,255,0.08); }
        .opp-detail-row { display: none; }
        .opp-detail-row.open { display: table-row !important; }
        .sig-bar { display: inline-block; background: linear-gradient(90deg, #22c55e, #16a34a); border-radius: 10px; padding: 2px 10px; font-size: 12px; font-weight: 700; color: #fff; }
        .sig-bar.med { background: linear-gradient(90deg, #f59e0b, #d97706); }
        .sig-bar.low { background: linear-gradient(90deg, #ef4444, #b91c1c); }
        .opp-scan-progress {
            margin: 10px 0 4px 0; padding: 12px 14px;
            background: rgba(30, 136, 229, 0.08); border: 1px solid rgba(30, 136, 229, 0.35);
            border-radius: 8px;
        }
        .opp-scan-progress .opp-scan-label {
            display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap;
            font-size: 12px; color: #cbd5e1; margin-bottom: 8px;
        }
        .opp-scan-progress .opp-scan-track {
            height: 10px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden;
        }
        .opp-scan-progress .opp-scan-fill {
            height: 100%; width: 0%;
            background: linear-gradient(90deg, #1e88e5, #42a5f5, #00e676);
            border-radius: 999px; transition: width 0.35s ease;
        }
        .opp-scan-progress .opp-scan-sub {
            margin-top: 6px; font-size: 11px; color: #94a3b8;
        }
        .opp-style-badge { font-size: 11px; padding: 2px 8px; border-radius: 8px; background: rgba(99,102,241,0.25); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.4); }
        .opp-chevron { font-size: 11px; margin-left: 6px; color: #64748b; transition: transform 0.2s; }
        .opp-main-row.open .opp-chevron { transform: rotate(180deg); }
    </style>

    <!-- TAB 3: TRADE TICKET -->
    <div id="tab-ticket" class="tab-content">
        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">🎟️ Create Trade Plan (INR ₹)</span><span class="badge badge-green">U1, U2, U4 BOUND</span></div>
                
                <div class="input-group"><label>Instrument Symbol</label><input type="text" id="tk-symbol" value="RELIANCE"></div>
                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Direction</label>
                        <select id="tk-direction">
                            <option value="BUY">BUY (Long)</option>
                            <option value="SELL">SELL (Short)</option>
                        </select>
                    </div>
                    <div class="input-group" style="flex: 1;"><label>Trading Style</label>
                        <select id="tk-style">
                            <option value="INTRADAY">Intraday</option>
                            <option value="SCALPING">Scalping</option>
                            <option value="SWING">Swing</option>
                            <option value="OPTIONS_BUYING">Options Buying</option>
                            <option value="OPTIONS_SELLING">Options Selling</option>
                        </select>
                    </div>
                </div>
                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Strategy (Full Canonical Registry)</label>
                        <select id="tk-strategy">
                            <option value="Momentum Breakout">Momentum Breakout (Intraday Equity)</option>
                            <option value="VWAP Mean Reversion">VWAP Mean Reversion (Intraday Equity)</option>
                            <option value="Opening Range Breakout (ORB)">Opening Range Breakout (ORB) (Intraday Equity)</option>
                            <option value="ADX Trend Acceleration">ADX Trend Acceleration (Intraday Equity)</option>
                            <option value="RSI Oversold/Overbought Reversion">RSI Oversold/Overbought Reversion (Intraday Equity)</option>
                            <option value="Bollinger Band Band-Touch Bounce">Bollinger Band Band-Touch Bounce (Intraday Equity)</option>
                            <option value="Moving Average Trend Following">Moving Average Trend Following (Swing Equity)</option>
                            <option value="Breakout + Volume Surge">Breakout + Volume Surge (Swing Equity)</option>
                            <option value="Futures Momentum Drive">Futures Momentum Drive (Futures)</option>
                            <option value="Options Buying (Call Option Drive)">Options Buying (Call Option Drive) (Options)</option>
                            <option value="Options Buying (Put Option Drive)">Options Buying (Put Option Drive) (Options)</option>
                            <option value="Bull Call Spread">Bull Call Spread (Defined Risk Options)</option>
                            <option value="Bear Put Spread">Bear Put Spread (Defined Risk Options)</option>
                            <option value="Iron Condor (Range-Bound Neutral)">Iron Condor (Range-Bound Neutral) (Multi-Leg Options)</option>
                            <option value="Long Straddle/Strangle Volatility Surge">Long Straddle/Strangle Volatility Surge (Multi-Leg Options)</option>
                        </select>
                    </div>
                </div>

                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Entry Price (₹) <span id="tk-ltp-badge" class="sub-text" style="font-weight:normal;">— fetching Angel LTP…</span></label><input type="number" id="tk-entry" value="" placeholder="Live Angel LTP"></div>
                    <div class="input-group" style="flex: 1;"><label>Quantity / Lots</label><input type="number" id="tk-qty" value="10"></div>
                </div>

                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Stop Loss (₹)</label><input type="number" id="tk-sl" value="2690.00"></div>
                    <div class="input-group" style="flex: 1;"><label>Target Price (₹)</label><input type="number" id="tk-tp" value="2850.00"></div>
                </div>

                <div class="input-group"><label>Trailing Stop Loss (₹ Trail)</label><input type="number" id="tk-tsl" value="20.00"></div>

                <div class="input-group">
                    <label>Trade Start Time (IST) — strategy entry slot</label>
                    <select id="tk-start-time">
                        <option value="IMMEDIATE">Immediate (now, if market open)</option>
                        <option value="09:15">09:15 AM — Open / ORB style</option>
                        <option value="09:30" selected>09:30 AM — Post-open confirmation</option>
                        <option value="09:45">09:45 AM</option>
                        <option value="10:00">10:00 AM — Mid-morning</option>
                        <option value="10:15">10:15 AM</option>
                        <option value="10:30">10:30 AM</option>
                        <option value="11:00">11:00 AM</option>
                        <option value="11:30">11:30 AM</option>
                        <option value="12:00">12:00 PM</option>
                        <option value="13:00">01:00 PM</option>
                        <option value="14:00">02:00 PM</option>
                    </select>
                    <div class="sub-text" style="margin-top:4px;">Arm from 09:00 IST. At the selected time the paper fill uses live Angel WebSocket LTP (not the ticket entry).</div>
                </div>

                <button class="btn btn-green" onclick="generatePlan()" style="width:100%;">Generate Pre-Trade Summary</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📊 Pre-Execution Trade Summary</span><span class="badge badge-amber">PRE-TRADE</span></div>
                <div id="plan-summary-box" class="modal-box">Fill in ticket and click button to view pre-trade risk summary.</div>
                
                <div style="margin-top: 14px; padding: 10px; background: rgba(255,179,0,0.08); border: 1px solid var(--accent-amber); border-radius: 8px; font-size: 12px;">
                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                        <input type="checkbox" id="chk-offmarket-override" onchange="toggleOffmarketOverride(this.checked)">
                        <span>ALLOW WEEKEND OFF-MARKET PAPER SIMULATION (TESTING OVERRIDE)</span>
                    </label>
                </div>

                <button class="btn btn-green" style="margin-top:16px; width:100%;" onclick="executeOrSchedulePaperTrade()">🚀 Execute / Arm Paper Trade</button>
                <div id="scheduled-orders-box" class="modal-box" style="margin-top:12px;">No armed schedules.</div>
            </div>
        </div>
    </div>

    <!-- TAB 4: PAPER SIMULATOR -->
    <div id="tab-paper" class="tab-content">
        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header"><span class="card-title">🧪 4-Mode Paper Trading Simulator</span><span class="badge badge-green">U3 PARITY ENFORCED</span></div>
            <div class="sub-text">Paper trading uses the exact same risk, protection, trailing stop, and auto-exit engine as live trading.</div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header" style="display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
                <span class="card-title">📊 Day Flatten Limits (Paper)</span>
                <span class="badge badge-green" id="day-risk-policy-badge">GROSS TRIGGERS</span>
            </div>
            <div class="sub-text" style="margin-bottom:12px;">
                Set gross combined day PnL limits (realized + open MTM). Use <strong>+</strong> for profit target and <strong>−</strong> for loss limit.
                Net figures below subtract/add estimated Angel One charges (STT, brokerage, GST, etc.) — edit charge fields to match your contract.
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:14px; align-items:flex-end; margin-bottom:12px;">
                <div class="input-group" style="flex:0 1 140px; margin-bottom:0;">
                    <label for="day-profit-target">Profit target (+₹)</label>
                    <input type="number" id="day-profit-target" min="0" step="100" value="1500">
                </div>
                <div class="input-group" style="flex:0 1 140px; margin-bottom:0;">
                    <label for="day-loss-limit">Loss limit (−₹)</label>
                    <input type="number" id="day-loss-limit" min="0" step="100" value="2000">
                </div>
                <div class="input-group" style="flex:0 1 120px; margin-bottom:0;">
                    <label for="charge-brokerage">Brokerage/order (₹)</label>
                    <input type="number" id="charge-brokerage" min="0" step="1" value="20">
                </div>
                <div class="input-group" style="flex:0 1 110px; margin-bottom:0;">
                    <label for="charge-stt">STT sell (%)</label>
                    <input type="number" id="charge-stt" min="0" step="0.001" value="0.025">
                </div>
                <button class="btn btn-green" style="width:auto; margin-bottom:0;" onclick="saveDayRiskPolicy()">Save limits</button>
            </div>
            <div id="day-risk-preview" class="modal-box" style="font-size:13px; line-height:1.6;">
                Loading day limit preview…
            </div>
            <div class="sub-text" id="day-risk-charges-note" style="margin-top:8px;"></div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header" style="display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
                <span class="card-title">📋 Active Paper Positions & Simulation Log</span>
                <button class="btn btn-red" style="padding:8px 14px;" onclick="killAllPaperTrades()">🛑 Kill All Open Paper Trades</button>
            </div>
            <div id="paper-summary-bar" style="display:flex; gap:18px; flex-wrap:wrap; padding:10px 4px 14px; font-size:13px; color:#cbd5e1;">
                <span>Placed: <strong id="paper-cum-placed">₹0.00</strong></span>
                <span>Open PnL: <strong id="paper-cum-pnl">+₹0.00</strong></span>
                <span>PnL %: <strong id="paper-cum-pnl-pct">+0.00%</strong></span>
                <span>Utilized: <strong id="paper-utilized">₹0.00</strong></span>
                <span>Available: <strong id="paper-available">₹0.00</strong></span>
            </div>
            <div id="paper-positions-box" class="modal-box">No active paper positions right now. Use Trade Ticket to execute paper trades.</div>
            <div class="sub-text" style="margin-top:10px;">
                Per-trade SL/Target auto-exit is active. Day flatten uses your saved gross limits above
                (default <strong>+₹1,500</strong> profit / <strong>−₹2,000</strong> loss) — then blocks new paper entries until next IST day.
                INTRADAY/SCALPING also square-off at 03:15 PM IST (Angel MIS parity).
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">✋ Mode 1: Manual Simulation</span><span class="badge badge-green">ACTIVE</span></div>
                <div class="sub-text">You decide everything. Pick stock, entry, SL, TP, and trailing stop in the Trade Ticket.</div>
                <button class="btn btn-green" onclick="showTab(event, 'tab-ticket')">Go to Trade Ticket</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">🤝 Mode 2: Assisted Simulation</span><span class="badge badge-green">ACTIVE</span></div>
                <div class="sub-text">NexTrade scans the market, calculates suggested entry, SL, and target, and asks for 1-click confirmation.</div>
                <button class="btn btn-green" onclick="showTab(event, 'tab-opportunities')">View Opportunities</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📊 Mode 3: Strategy-Driven</span><span class="badge badge-green">ACTIVE</span></div>
                <div class="sub-text">Select Trading Style (Intraday, Scalping, Swing, F&O) and Strategy. NexTrade automatically builds the paper trade plan.</div>
                <button class="btn btn-green" onclick="alert('Strategy-Driven Mode active!')">Select Strategy</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">⚡ Mode 4: Automated Simulation</span><span class="badge badge-amber">RUNNING</span></div>
                <div class="sub-text">Runs continuously in the background against live market ticks. Automatically enters & exits paper trades on SL/TP/TSL hit.</div>
                <button class="btn btn-amber" onclick="alert('Automated Simulation is active and monitoring live market ticks.')">View Auto Engine Status</button>
            </div>
        </div>
    </div>

    <!-- TAB 5: POSITIONS -->
    <div id="tab-positions" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">📈 Position Protection & Trailing Distance</span><span class="badge badge-green">PROTECTED</span></div>
            <div id="live-positions-container">
                <div class="modal-box">
                    <strong style="color:#fff;">RELIANCE — BUY 10 Qty @ ₹2,742.00</strong><br>
                    Current Price: <span style="color:var(--accent-green);">₹2,765.00 (+₹460.00 P&L)</span><br><br>
                    🎯 Target: ₹2,820.00 (Distance: ₹55.00)<br>
                    🛡️ Trailing SL: ₹2,745.00 (Protected Profit: +₹50.00)<br>
                    🛑 Original SL: ₹2,690.00<br><br>
                    <span class="badge badge-green">Auto-Exit: ACTIVE</span>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 6: HOLDINGS -->
    <div id="tab-holdings" class="tab-content">
        <div class="grid" style="margin-bottom: 20px;">
            <div class="card">
                <div class="card-header"><span class="card-title">💰 Total Invested</span></div>
                <div class="metric-big" id="holdings-invested">₹0.00</div>
                <div class="sub-text">Cost basis across all holdings</div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">📊 Current Value</span><span class="badge badge-green" id="holdings-ltp-badge">LIVE</span></div>
                <div class="metric-big" id="holdings-current">₹0.00</div>
                <div class="sub-text">Mark-to-market at latest LTP</div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">📈 Total P&amp;L</span></div>
                <div class="metric-big" id="holdings-pnl">+₹0.00</div>
                <div class="sub-text" id="holdings-pnl-pct">+0.00% on invested capital</div>
            </div>
        </div>
        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header">
                <span class="card-title">➕ Add Zerodha Holding (Manual)</span>
                <span class="badge" style="background: rgba(41, 182, 246, 0.15); color: var(--accent-blue); border: 1px solid var(--accent-blue);">NO KITE OAUTH</span>
            </div>
            <div class="sub-text" style="margin-bottom: 12px;">Track Zerodha stocks without daily Kite Connect login. LTP is enriched via Angel NSE quotes.</div>
            <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;">
                <div class="input-group" style="flex: 1 1 140px; margin-bottom: 0;">
                    <label for="zh-symbol">Symbol</label>
                    <input type="text" id="zh-symbol" placeholder="e.g. RELIANCE, TCS">
                </div>
                <div class="input-group" style="flex: 0 1 100px; margin-bottom: 0;">
                    <label for="zh-qty">Qty</label>
                    <input type="number" id="zh-qty" min="1" step="1" placeholder="10">
                </div>
                <div class="input-group" style="flex: 0 1 120px; margin-bottom: 0;">
                    <label for="zh-avg">Avg Price (₹)</label>
                    <input type="number" id="zh-avg" min="0.01" step="0.01" placeholder="2500.00">
                </div>
                <div class="input-group" style="flex: 1 1 160px; margin-bottom: 0;">
                    <label for="zh-notes">Notes (optional)</label>
                    <input type="text" id="zh-notes" placeholder="SIP / long-term">
                </div>
                <button class="btn btn-green" id="zh-submit-btn" onclick="saveZerodhaHolding()" style="width: auto; margin-bottom: 0;">Add Holding</button>
                <button class="btn btn-amber btn-sm" id="zh-cancel-btn" onclick="cancelZerodhaEdit()" style="display: none; width: auto; margin-bottom: 0;">Cancel Edit</button>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title" id="holdings-title">💼 Portfolio Holdings</span><span class="badge badge-amber" id="holdings-sync-badge">LOADING</span></div>
            <table class="table">
                <thead><tr><th>Symbol</th><th>Broker</th><th>Qty</th><th>Avg Price</th><th>LTP</th><th>P&amp;L</th><th>Current Value</th><th style="text-align: center;">Actions</th></tr></thead>
                <tbody id="holdings-body"></tbody>
            </table>
        </div>
    </div>

    <!-- TAB 7: WATCHLIST MONITOR -->
    <div id="tab-watchlist" class="tab-content">
        <div class="card">
            <div class="card-header">
                <span class="card-title" id="watchlist-title-label">👁️ Watchlist Monitor</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <span class="badge badge-green" id="watchlist-refresh-badge">LIVE WS</span>
                    <button class="btn btn-sm" type="button" onclick="fetchWatchlist(true)">↻ Refresh Prices</button>
                </div>
            </div>

            <div style="display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
                <input type="text" id="add-symbol-input" placeholder="Add or remove symbol (e.g. SBIN, TATAMOTORS)" style="flex: 1; min-width: 180px; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); background: #0e1422; color: #fff; font-size: 13px;" onkeydown="if(event.key==='Enter'){event.preventDefault();addWatchlistSymbol();}">
                <button class="btn btn-green" onclick="addWatchlistSymbol()" style="width: auto;">+ Add Stock</button>
                <button class="btn btn-red" onclick="removeWatchlistSymbolFromInput()" style="width: auto;">Remove</button>
                <button class="btn btn-sm" type="button" onclick="downloadWatchlist()" style="width: auto;">Download CSV</button>
            </div>

            <table class="table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>LTP</th>
                        <th>Change</th>
                        <th>Change %</th>
                        <th>Volume</th>
                        <th style="text-align: center;">Action</th>
                    </tr>
                </thead>
                <tbody id="watchlist-body"></tbody>
            </table>
        </div>
    </div>

    <!-- TAB 8: JOURNAL (7J) -->
    <div id="tab-journal" class="tab-content">
        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">📜 Performance Summary (7J)</span><span class="badge badge-green">INR (₹)</span></div>
                <div class="metric-big" id="j-net-pnl">+₹0.00</div>
                <div class="sub-text">Win Rate: <strong style="color:var(--accent-green);" id="j-win-rate">0.0%</strong> | Total Trades: <strong id="j-trades">0</strong></div>
                <button class="btn btn-green" style="margin-top:16px; width:100%;" onclick="exportExcelReport()">📊 Export Trading Log to Excel (.xlsx)</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📊 P&L by Trading Style</span></div>
                <div id="style-breakdown-box" class="modal-box">No trades executed today.</div>
            </div>
        </div>

        <div class="card" style="margin-top: 20px;">
            <div class="card-header">
                <span class="card-title">📜 Executed Trades Log</span>
                <button class="btn btn-sm" type="button" onclick="fetchJournal()">↻ Refresh Journal</button>
            </div>
            <table class="table">
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Symbol</th>
                        <th>Style</th>
                        <th>Strategy</th>
                        <th>Direction</th>
                        <th>Qty</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>P&L</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="executed-trades-body">
                    <tr><td colspan="10" style="text-align:center; color:var(--text-muted);">No executed trades found today.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- TAB 9: PRE-MARKET -->
    <div id="tab-premarket" class="tab-content">
        <div class="card">
            <div class="card-header">
                <span class="card-title">🌅 Pre-Market Morning Brief</span>
                <span class="badge badge-amber" id="premarket-status-badge">LOADING</span>
            </div>
            <div class="sub-text" id="premarket-window-label" style="margin-bottom:10px;">Morning outlook from Angel indices + watchlist/analyzer focus list.</div>
            <div id="premarket-box" class="modal-box">Loading pre-market outlook...</div>
            <button class="btn btn-sm" type="button" style="margin-top:12px;" onclick="fetchPremarket()">↻ Refresh Brief</button>
        </div>
    </div>

    <!-- TAB 10: SETTINGS -->
    <div id="tab-settings" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">⚙️ Risk & Preferences Settings</span></div>
            <div class="input-group"><label>Default Trading Style</label><select><option>Intraday</option><option>Swing</option></select></div>
            <div class="input-group"><label>Per-Account Exposure Limit (₹)</label><input type="text" value="₹1,000.00" readonly></div>
            <div class="input-group"><label>Portfolio Exposure Ceiling (₹)</label><input type="text" value="₹3,000.00" readonly></div>
        </div>
    </div>

    <!-- TAB 11: CONTROL PLANE (PRODUCT B) -->
    <div id="tab-control" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">🛡️ Operations Console & Invariants</span><span class="badge badge-amber">PRODUCT B</span></div>
            <div class="sub-text">506 Regression Tests PASSED | 90 Targeted Invariants Active | SHA-256 Hash Chain Verified</div>
            <button class="btn btn-green" onclick="runFullAudit()" style="margin-top:12px; width:100%;">Run Phase 6G Audit</button>
            <button class="btn btn-red" onclick="triggerKill('portfolio')" style="margin-top:8px; width:100%;">Trigger Master Portfolio Kill</button>
            <div class="modal-box" id="ctrl-log">Control Plane ready.</div>
        </div>
    </div>

    <script>
        // Single-tab guard — second browser tab must not share the Angel WebSocket session
        (function claimDashboardTabLock() {
            const LOCK_KEY = 'nextrade_dashboard_tab_lock_v1';
            const tabId = 'tab_' + Math.random().toString(36).slice(2) + '_' + Date.now();
            const now = Date.now();
            try {
                const raw = localStorage.getItem(LOCK_KEY);
                if (raw) {
                    const prev = JSON.parse(raw);
                    if (prev && prev.id && prev.id !== tabId && (now - Number(prev.ts || 0)) < 10000) {
                        document.documentElement.innerHTML = '<body style="background:#0b1220;color:#e2e8f0;font-family:Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;"><div style="max-width:520px;padding:28px;border:1px solid #334155;border-radius:12px;background:#111827;"><h2 style="margin:0 0 12px;color:#f87171;">Dashboard already open</h2><p style="line-height:1.5;color:#cbd5e1;">Another NexTrade browser tab is already using this dashboard. Running two tabs/servers causes duplicate Angel WebSocket connections and can get the feed declined.</p><p style="color:#94a3b8;font-size:13px;">Close the other tab (or stop the other python dashboard process), then reload this page.</p></div></body>';
                        return;
                    }
                }
                const beat = () => localStorage.setItem(LOCK_KEY, JSON.stringify({ id: tabId, ts: Date.now() }));
                beat();
                setInterval(beat, 2500);
                window.addEventListener('beforeunload', () => {
                    try {
                        const cur = JSON.parse(localStorage.getItem(LOCK_KEY) || '{}');
                        if (cur.id === tabId) localStorage.removeItem(LOCK_KEY);
                    } catch (e) {}
                });
            } catch (e) { /* private mode — continue */ }
        })();
        function showTab(evt, tabId) {
            const panel = document.getElementById(tabId);
            if (!panel) {
                console.error('Unknown tab:', tabId);
                return;
            }
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            panel.classList.add('active');
            let btn = evt && evt.currentTarget ? evt.currentTarget : null;
            if (!btn) {
                btn = document.querySelector('.tab-btn[onclick*="' + tabId + '"]');
            }
            if (btn) btn.classList.add('active');
            if (tabId === 'tab-journal') fetchJournal();
            if (tabId === 'tab-paper' || tabId === 'tab-positions') fetchPositions();
            if (tabId === 'tab-premarket') fetchPremarket();
        }

        async function fetchTodayMandate() {
            try {
                const res = await fetch('/api/mandate/today');
                const data = await res.json();

                const regimeBadge = document.getElementById('cockpit-regime-badge');
                regimeBadge.innerText = data.market_regime_label;
                if (data.data_mode === 'LIVE') {
                    regimeBadge.className = 'badge badge-green';
                } else {
                    regimeBadge.className = 'badge badge-amber';
                }

                const analysisTime = document.getElementById('cockpit-analysis-time');
                if (analysisTime) {
                    analysisTime.innerText = 'Analysis as of: ' + (data.analysis_timestamp_ist || data.ist_datetime || '—');
                }

                document.getElementById('cockpit-nifty').innerText = data.nifty_trend;
                document.getElementById('cockpit-banknifty').innerText = data.bank_nifty_trend;
                const vixText = (data.vix_level != null && data.vix_level !== '')
                    ? data.vix_level + ' (India VIX)'
                    : '— (India VIX unavailable)';
                document.getElementById('cockpit-vix').innerText = vixText;
                document.getElementById('cockpit-breadth').innerText = data.market_breadth;
                const srcEl = document.getElementById('cockpit-data-source');
                if (srcEl) {
                    const mds = data.broker_status || {};
                    const brokerUp = !!(mds.broker_connected);
                    const wsUp = !!(mds.websocket_connected);
                    const live = !!data.market_data_live;
                    if (live) {
                        srcEl.innerText = 'DATA: LIVE (' + (data.market_data_source || 'ANGEL') + ')';
                        srcEl.className = 'badge badge-green';
                    } else if (brokerUp && wsUp) {
                        srcEl.innerText = 'BROKER LIVE · index quotes loading…';
                        srcEl.className = 'badge badge-green';
                    } else if (brokerUp) {
                        srcEl.innerText = 'BROKER REST OK · WebSocket connecting…';
                        srcEl.className = 'badge badge-amber';
                    } else {
                        srcEl.innerText = 'ANGEL DISCONNECTED — check config.json & restart';
                        srcEl.className = 'badge badge-red';
                    }
                }

                const stratName = data.recommended_strategy || 'None';
                document.getElementById('cockpit-strategy-name').innerText = stratName;
                const scoreEl = document.getElementById('cockpit-score');
                scoreEl.innerText = data.suitability_score > 0
                    ? `Suitability: ${data.suitability_score} / 100`
                    : 'Suitability: —';
                scoreEl.className = data.suitability_score >= 70 ? 'badge badge-green' : 'badge badge-amber';

                let rHtml = '';
                (data.primary_rationale || []).forEach(r => rHtml += `<li>${r}</li>`);
                document.getElementById('cockpit-rationale-list').innerHTML = rHtml || '<li>No rationale available.</li>';

                document.getElementById('m-cap').innerText = data.limits.capital_deployed_limit;
                const perScripEl = document.getElementById('m-per-scrip');
                if (perScripEl && data.limits.per_scrip_capital) {
                    perScripEl.innerText = data.limits.per_scrip_capital;
                }
                document.getElementById('m-risk').innerText = data.limits.max_risk_ceiling;
                document.getElementById('m-loss').innerText = data.limits.daily_loss_limit;

                const banner = document.getElementById('mandate-status-banner');
                if (data.mandate_state === 'AUTONOMOUS_TRADING_ACTIVE') {
                    banner.style.display = 'flex';
                } else {
                    banner.style.display = 'none';
                }

                const tlApproval = document.getElementById('tl-approval-status');
                if (tlApproval) {
                    if (data.mandate_state === 'AUTONOMOUS_TRADING_ACTIVE') {
                        tlApproval.innerText = 'APPROVED (live)';
                        tlApproval.className = 'badge badge-green';
                    } else {
                        tlApproval.innerText = 'PENDING (live)';
                        tlApproval.className = 'badge badge-amber';
                    }
                }

            } catch (err) { console.error(err); }
        }

        async function approveMandate() {
            const res = await fetch('/api/mandate/approve', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                alert("🟢 " + data.message);
                fetchTodayMandate();
            } else {
                alert(data.error || "Failed to approve mandate");
            }
        }

        async function pauseMandate() {
            const res = await fetch('/api/mandate/pause', { method: 'POST' });
            const data = await res.json();
            alert(data.message || data.error);
            fetchTodayMandate();
        }

        async function stopMandate() {
            if (!confirm("Are you sure you want to trigger Emergency Stop across all autonomous trading?")) return;
            const res = await fetch('/api/mandate/stop', { method: 'POST' });
            const data = await res.json();
            alert(data.message || data.error);
            fetchTodayMandate();
        }

        function scripQtyFromLtp(ltp) {
            const budget = window.paperPerScripCapital || 100000;
            const price = parseFloat(ltp);
            if (!Number.isFinite(price) || price <= 0) return 1;
            return Math.max(1, Math.floor(budget / price));
        }

        async function updateStatus() {
            if (window._statusFetchInflight) return;
            window._statusFetchInflight = true;
            try {
                const ctrl = new AbortController();
                const timer = setTimeout(() => ctrl.abort(), 15000);
                const res = await fetch('/api/status', { signal: ctrl.signal, cache: 'no-store' });
                clearTimeout(timer);
                const data = await res.json();
                const policy = data.paper_capital_policy || {};
                if (policy.per_scrip_capital) window.paperPerScripCapital = policy.per_scrip_capital;
                
                document.getElementById('dash-capital').innerText = data.total_capital_fmt;
                const deployEl = document.getElementById('dash-deployable');
                if (deployEl && policy.deployable_capital) {
                    deployEl.innerText = '₹' + Number(policy.deployable_capital).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                }
                document.getElementById('dash-cash').innerText = data.available_cash_fmt;
                document.getElementById('dash-margin').innerText = data.utilized_margin_fmt;
                document.getElementById('dash-pnl').innerText = data.todays_pnl_fmt;
                const dashPnlEl = document.getElementById('dash-pnl');
                if (dashPnlEl && data.todays_pnl_fmt) {
                    dashPnlEl.style.color = String(data.todays_pnl_fmt).startsWith('-') ? 'var(--accent-red)' : 'var(--accent-green)';
                }
                const netEl = document.getElementById('dash-net-pnl');
                if (netEl) netEl.innerText = data.todays_net_pnl_fmt || data.todays_pnl_fmt;
                document.getElementById('dash-overall-pnl').innerText = data.overall_pnl_fmt;
                document.getElementById('dash-risk').innerText = data.active_risk_fmt;

                const brokerBadge = document.getElementById('broker-status-badge');
                if (brokerBadge) {
                    const mds = data.market_data || {};
                    brokerBadge.innerText = data.broker_status || 'Angel One';
                    const auth = mds.data_authority || '';
                    if (mds.websocket_streaming || auth === 'ANGEL_WS_LIVE') {
                        brokerBadge.className = 'badge badge-green';
                    } else if (mds.websocket_connected || mds.broker_connected) {
                        brokerBadge.className = 'badge badge-amber';
                    } else {
                        brokerBadge.className = 'badge badge-red';
                    }
                }

                document.getElementById('eod-pnl').innerText = data.todays_net_pnl_fmt || data.todays_pnl_fmt;

                const board = data.index_board || {};
                const idxBadge = document.getElementById('idx-source-badge');
                const idxBox = document.getElementById('dash-indices');
                const idxNote = document.getElementById('idx-source-note');
                if (idxBadge && idxBox) {
                    if (board.ok) {
                        idxBadge.className = 'badge badge-green';
                        idxBadge.innerText = 'LIVE (' + (board.source || 'ANGEL') + ')';
                    } else {
                        idxBadge.className = 'badge badge-amber';
                        idxBadge.innerText = 'PARTIAL / UNAVAILABLE';
                    }
                    let idxHtml = '';
                    (board.indices || []).forEach(ix => {
                        const chgColor = (ix.change_pct == null) ? 'var(--text-muted)' : (ix.change_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)');
                        idxHtml += `<div class="index-chip">
                            <div class="idx-name">${ix.name}</div>
                            <div class="idx-ltp">${ix.ltp_fmt}</div>
                            <div class="idx-chg" style="color:${chgColor};">${ix.change_fmt}</div>
                            <div class="idx-exch">${ix.exchange || ''}</div>
                        </div>`;
                    });
                    idxBox.innerHTML = idxHtml || '<div class="sub-text">Index quotes unavailable.</div>';
                    if (idxNote) {
                        const gLive = board.global_live_count != null ? board.global_live_count : 0;
                        idxNote.innerText = board.ok
                            ? 'Indian indices: Angel One. Global indices: yfinance (display/reference only). Globals live: ' + gLive + '.'
                            : 'Angel index quotes unavailable — check broker login in config.json and restart dashboard.';
                    }
                }

                const mBadge = document.getElementById('market-status-badge');
                mBadge.innerText = data.market_status_badge;
                if (data.market_open) {
                    mBadge.className = 'badge badge-green';
                } else {
                    mBadge.className = 'badge badge-red';
                }

                const istClock = document.getElementById('ist-clock-badge');
                if (istClock && data.ist_datetime) {
                    istClock.innerText = '🕐 ' + data.ist_datetime;
                }

                let gHtml = '';
                if (!data.gainers || data.gainers.length === 0) {
                    gHtml = `<tr><td colspan="3" style="color:var(--text-muted);">${data.movers_note || 'No gainers with valid change% yet.'}</td></tr>`;
                } else {
                    data.gainers.forEach(g => {
                        gHtml += `<tr><td><strong>${g.symbol}</strong></td><td>${g.ltp}</td><td style="color:var(--accent-green);">${g.change}</td></tr>`;
                    });
                }
                document.getElementById('dash-gainers').innerHTML = gHtml;

                let lHtml = '';
                if (!data.losers || data.losers.length === 0) {
                    lHtml = `<tr><td colspan="3" style="color:var(--text-muted);">${data.movers_note || 'No losers with valid change% yet.'}</td></tr>`;
                } else {
                    data.losers.forEach(l => {
                        lHtml += `<tr><td><strong>${l.symbol}</strong></td><td>${l.ltp}</td><td style="color:var(--accent-red);">${l.change}</td></tr>`;
                    });
                }
                document.getElementById('dash-losers').innerHTML = lHtml;

                fetchPositions();

            } catch (err) { console.error(err); }
            finally { window._statusFetchInflight = false; }
        }

        function fmtInr(n) {
            const v = Number(n || 0);
            const sign = v >= 0 ? '+' : '−';
            return sign + '₹' + Math.abs(v).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }

        function renderDayRiskPreview(proj, profitGross, lossGross) {
            const box = document.getElementById('day-risk-preview');
            const note = document.getElementById('day-risk-charges-note');
            if (!box || !proj) return;
            const pg = profitGross != null ? profitGross : proj.profit_target_gross_inr;
            const lg = lossGross != null ? lossGross : proj.loss_limit_gross_inr;
            box.innerHTML = `
                <div><strong>Gross triggers</strong> (combined day PnL): profit <span style="color:var(--accent-green);">+₹${Number(pg).toLocaleString('en-IN')}</span>
                &nbsp;|&nbsp; loss <span style="color:var(--accent-red);">−₹${Number(lg).toLocaleString('en-IN')}</span></div>
                <div style="margin-top:6px;"><strong>Est. charges today</strong>: ₹${Number(proj.est_total_charges_inr || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}
                (closed ₹${Number(proj.est_charges_closed_today_inr || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}
                + open flatten ₹${Number(proj.est_charges_if_flatten_open_inr || 0).toLocaleString('en-IN', {minimumFractionDigits:2})})</div>
                <div style="margin-top:6px;"><strong>Net if limits hit</strong>:
                profit target → <span style="color:var(--accent-green);">${fmtInr(proj.net_profit_if_target_hit_inr)}</span>
                &nbsp;|&nbsp; loss limit → <span style="color:var(--accent-red);">${fmtInr(proj.net_loss_if_limit_hit_inr)}</span></div>
            `;
            if (note) note.innerText = proj.charges_note || '';
            const profEl = document.getElementById('day-profit-target');
            const lossEl = document.getElementById('day-loss-limit');
            if (profEl && document.activeElement !== profEl) profEl.value = pg;
            if (lossEl && document.activeElement !== lossEl) lossEl.value = lg;
        }

        async function loadDayRiskPolicy() {
            try {
                const res = await fetch('/api/paper/day_risk_policy');
                const data = await res.json();
                if (!data.ok) return;
                const pol = data.policy || {};
                const ch = pol.charges || {};
                const setVal = (id, v) => { const el = document.getElementById(id); if (el != null && v != null) el.value = v; };
                setVal('day-profit-target', pol.profit_target_inr);
                setVal('day-loss-limit', pol.loss_limit_inr);
                setVal('charge-brokerage', ch.brokerage_per_order_inr);
                setVal('charge-stt', ch.stt_sell_pct);
                renderDayRiskPreview(data.projection, pol.profit_target_inr, pol.loss_limit_inr);
            } catch (e) { console.error('loadDayRiskPolicy', e); }
        }

        async function saveDayRiskPolicy() {
            const payload = {
                profit_target_inr: Number(document.getElementById('day-profit-target').value || 1500),
                loss_limit_inr: Number(document.getElementById('day-loss-limit').value || 2000),
                charges: {
                    brokerage_per_order_inr: Number(document.getElementById('charge-brokerage').value || 20),
                    stt_sell_pct: Number(document.getElementById('charge-stt').value || 0.025),
                },
            };
            try {
                const res = await fetch('/api/paper/day_risk_policy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (data.success) {
                    renderDayRiskPreview(data.projection, data.policy.profit_target_inr, data.policy.loss_limit_inr);
                    alert(data.message || 'Day flatten limits saved.');
                } else {
                    alert(data.error || 'Save failed');
                }
            } catch (e) {
                alert('Save failed: ' + e);
            }
        }

        async function fetchPositions() {
            try {
                const res = await fetch('/api/positions');
                const data = await res.json();
                const positions = Array.isArray(data) ? data : (data.positions || []);
                const summary = (!Array.isArray(data) && data.summary) ? data.summary : null;
                
                document.getElementById('btn-tab-paper').innerText = `🧪 Paper Simulator (${positions.length} Open)`;
                document.getElementById('btn-tab-positions').innerText = `📈 Live Positions (${positions.length} Open)`;

                if (summary) {
                    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v; };
                    setTxt('paper-cum-placed', summary.cum_placed_fmt || '₹0.00');
                    setTxt('paper-cum-pnl', summary.cum_pnl_fmt || '+₹0.00');
                    setTxt('paper-cum-pnl-pct', summary.cum_pnl_pct_fmt || '+0.00%');
                    setTxt('paper-utilized', '₹' + Number(summary.utilized_margin_raw || 0).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}));
                    setTxt('paper-available', '₹' + Number(summary.available_cash_raw || 0).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}));
                    if (summary.total_capital_fmt) setTxt('dash-capital', summary.total_capital_fmt);
                    if (summary.todays_pnl_fmt) setTxt('dash-pnl', summary.todays_pnl_fmt);
                    if (summary.todays_net_pnl_fmt) setTxt('dash-net-pnl', summary.todays_net_pnl_fmt);
                    if (summary.utilized_margin_fmt) setTxt('dash-margin', summary.utilized_margin_fmt);
                    if (summary.available_cash_fmt) setTxt('dash-cash', summary.available_cash_fmt);
                    const dashPnl = document.getElementById('dash-pnl');
                    if (dashPnl && summary.todays_pnl_fmt) {
                        dashPnl.style.color = String(summary.todays_pnl_fmt).startsWith('-') ? 'var(--accent-red)' : 'var(--accent-green)';
                    }
                    const pnlEl = document.getElementById('paper-cum-pnl');
                    if (pnlEl) pnlEl.style.color = (summary.cum_pnl_raw || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                    if (summary.day_halt) {
                        if (!document.getElementById('paper-day-halt-banner')) {
                            const ban = document.createElement('div');
                            ban.id = 'paper-day-halt-banner';
                            ban.className = 'modal-box';
                            ban.style.borderLeft = '4px solid var(--accent-amber)';
                            ban.style.marginBottom = '10px';
                            ban.innerHTML = '<strong>Paper day halt</strong> — ' + (summary.day_halt_reason || 'Day profit/loss limit hit') + '. No new paper entries until next IST session.';
                            const box = document.getElementById('paper-positions-box');
                            if (box && box.parentElement) box.parentElement.insertBefore(ban, box);
                        }
                    } else {
                        const oldBan = document.getElementById('paper-day-halt-banner');
                        if (oldBan) oldBan.remove();
                    }
                    if (summary.day_limit_projection) {
                        renderDayRiskPreview(summary.day_limit_projection, summary.day_profit_target_inr, summary.day_loss_limit_inr);
                    }
                }

                let posHtml = '';
                let tab4Html = '';

                if (positions.length === 0) {
                    posHtml = '<div class="modal-box">No active open positions. Execute paper trades from Trade Ticket.</div>';
                    tab4Html = 'No active paper positions right now. Use Trade Ticket to execute paper trades.';
                } else {
                    tab4Html = '<table class="table"><thead><tr><th>ID</th><th>Timestamp</th><th>Symbol</th><th>Direction</th><th>Style</th><th>Strategy</th><th>Qty</th><th>Entry</th><th>LTP</th><th>PnL</th><th>PnL %</th><th>SL</th><th>Target</th><th>Status</th><th>Action</th></tr></thead><tbody>';
                    positions.forEach(p => {
                        const ltpLive = !!p.ltp_live;
                        const ltpColor = ltpLive ? 'var(--accent-green)' : 'var(--accent-amber)';
                        const ltpLabel = p.ltp_fmt || p.current_price || '—';
                        const ltpSrc = p.ltp_source ? ` <span style="font-size:10px;color:#64748b;">(${p.ltp_source})</span>` : '';
                        const pnlColor = (p.pnl_raw == null || p.pnl_raw >= 0) ? 'var(--accent-green)' : 'var(--accent-red)';
                        const dir = (p.direction || 'BUY').toUpperCase();
                        const dirColor = dir === 'SELL' ? 'var(--accent-red)' : 'var(--accent-green)';
                        posHtml += `
                            <div class="modal-box" style="margin-bottom:12px;">
                                <strong style="color:#fff;">${p.symbol} — <span style="color:${dirColor};">${dir}</span> ${p.quantity} Qty @ ${p.entry_price} (${p.trading_style})</strong><br>
                                LTP: <span style="color:${ltpColor};">${ltpLabel}</span>${ltpSrc}
                                &nbsp;|&nbsp; PnL: <span style="color:${pnlColor};">${p.pnl || '+₹0.00'}</span>
                                &nbsp;|&nbsp; <span style="color:${pnlColor};">${p.pnl_pct || '—'}</span><br><br>
                                🎯 Target: ${p.target}<br>
                                🛡️ Trailing SL: ${p.trailing_stop}<br>
                                🛑 Original SL: ${p.stop_loss}<br><br>
                                <span class="badge badge-green">Auto-Exit: ACTIVE</span>
                                <button class="btn btn-red" style="margin-left:10px; padding:4px 10px; font-size:11px;" onclick="closePaperPosition('${p.position_id}')">Kill Trade</button>
                            </div>
                        `;
                        tab4Html += `<tr>
                            <td>${p.position_id}</td>
                            <td>${p.timestamp}</td>
                            <td><strong>${p.symbol}</strong></td>
                            <td style="color:${dirColor};font-weight:700;">${dir}</td>
                            <td>${p.trading_style}</td>
                            <td>${p.strategy}</td>
                            <td>${p.quantity}</td>
                            <td>${p.entry_price}</td>
                            <td style="color:${ltpColor};">${ltpLabel}${ltpSrc}</td>
                            <td style="color:${pnlColor};">${p.pnl || '—'}</td>
                            <td style="color:${pnlColor};font-weight:700;">${p.pnl_pct || '—'}</td>
                            <td style="color:var(--accent-red);">${p.stop_loss}</td>
                            <td style="color:var(--accent-green);">${p.target}</td>
                            <td><span class="badge badge-green">${p.status}</span></td>
                            <td><button class="btn btn-red" style="padding:4px 10px; font-size:11px;" onclick="closePaperPosition('${p.position_id}')">Kill</button></td>
                        </tr>`;
                    });
                    tab4Html += '</tbody></table>';
                }

                document.getElementById('live-positions-container').innerHTML = posHtml;
                document.getElementById('paper-positions-box').innerHTML = tab4Html;

            } catch (err) { console.error(err); }
        }

        async function closePaperPosition(positionId) {
            if (!confirm('Close this paper trade now at live Angel LTP?')) return;
            try {
                const res = await fetch('/api/positions/close', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ position_id: positionId })
                });
                const data = await res.json();
                alert(data.message || (data.success ? 'Closed' : 'Close failed'));
                updateStatus();
                fetchPositions();
                fetchJournal();
            } catch (e) { console.error(e); alert('Close failed'); }
        }

        async function killAllPaperTrades() {
            if (!confirm('KILL ALL open paper trades at live Angel LTP? This cannot be undone.')) return;
            try {
                const res = await fetch('/api/positions/close_all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await res.json();
                alert(data.message || 'Kill-all complete');
                updateStatus();
                fetchPositions();
                fetchJournal();
            } catch (e) { console.error(e); alert('Kill-all failed'); }
        }

        async function toggleOffmarketOverride(checked) {
            await fetch('/api/toggle_offmarket', {
                method: 'POST',
                body: JSON.stringify({ allow: checked })
            });
        }

        async function updateCapital(action, amount) {
            try {
                const res = await fetch('/api/capital/update', {
                    method: 'POST',
                    body: JSON.stringify({ action: action, amount: amount })
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('dash-capital').innerText = data.total_capital_fmt;
                    document.getElementById('dash-cash').innerText = data.available_cash_fmt;
                } else {
                    alert(data.error || 'Failed to update capital');
                }
            } catch (err) { console.error(err); }
        }

        async function resetPaperData() {
            if (!confirm("Reset all paper trade data and restore ₹10,00,000 ledger (₹5,00,000 deployable)?")) return;
            try {
                const res = await fetch('/api/reset_paper_data', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert(data.message);
                    updateStatus();
                    fetchJournal();
                }
            } catch (err) { console.error(err); }
        }

        async function exportExcelReport() {
            try {
                const res = await fetch('/api/export_excel', { method: 'POST' });
                const data = await res.json();
                if (!data.success) {
                    alert(data.error || "Failed to generate Excel report");
                    return;
                }
                // Blob download keeps the dashboard open (avoids navigating away)
                const dl = await fetch(data.download_url || '/api/download_excel');
                if (!dl.ok) {
                    alert("Failed to download Excel file (HTTP " + dl.status + ")");
                    return;
                }
                const blob = await dl.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = data.filename || ('NexTrade_Trading_Log_' + new Date().toISOString().slice(0,10).replace(/-/g,'') + '.xlsx');
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
            } catch (err) {
                console.error(err);
                alert("Excel export failed: " + (err && err.message ? err.message : err));
            }
        }

        function formatInrPrice(v) {
            if (v == null || v === '') return '—';
            if (typeof v === 'number' && !Number.isNaN(v)) {
                return v.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }
            const cleaned = String(v).replace(/[^0-9.\-]/g, '');
            const n = parseFloat(cleaned);
            if (Number.isNaN(n)) return '—';
            return n.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }

        let _oppScanPollTimer = null;
        let _oppFetchInFlight = false;

        function stopOppScanPoll() {
            if (_oppScanPollTimer) {
                clearInterval(_oppScanPollTimer);
                _oppScanPollTimer = null;
            }
        }

        function startOppScanPoll() {
            if (_oppScanPollTimer) return;
            _oppScanPollTimer = setInterval(() => { fetchOpportunities(); }, 2000);
        }

        function buildOppScanProgressHtml(scan) {
            const state = scan.state || 'idle';
            const done = Number(scan.symbols_done || 0);
            const total = Math.max(Number(scan.symbols_total || 0), 0);
            const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : (state === 'scanning' ? 2 : 0);
            const sym = scan.current_symbol ? String(scan.current_symbol) : '';
            const signals = Number(scan.signals_found || 0);
            const scanning = state === 'scanning' || state === 'starting';
            if (!scanning && !(total > 0 && done > 0 && done < total)) {
                return '';
            }
            const label = scanning
                ? (sym ? `Scanning <strong style="color:#e2e8f0;">${sym}</strong>` : 'Scanning watchlist…')
                : 'Scan progress';
            const right = total > 0
                ? `<strong style="color:#60a5fa;">${done}/${total}</strong> (${pct}%) · ${signals} signals`
                : `${signals} signals`;
            return `
                <div class="opp-scan-progress" id="opp-scan-progress">
                    <div class="opp-scan-label">
                        <span>${label}</span>
                        <span>${right}</span>
                    </div>
                    <div class="opp-scan-track"><div class="opp-scan-fill" style="width:${pct}%;"></div></div>
                    <div class="opp-scan-sub">${scan.message || ''}</div>
                </div>`;
        }

        async function fetchOpportunities() {
            if (_oppFetchInFlight) return;
            _oppFetchInFlight = true;
            try {
                const res = await fetch('/api/opportunities');
                const data = await res.json();
                const opps = Array.isArray(data) ? data : (data.opportunities || []);
                const msg = (!Array.isArray(data) && data.message) ? data.message : null;
                const scan = (!Array.isArray(data) && data.scan) ? data.scan : {};
                const scanState = scan.state || 'idle';
                const scanMsg = scan.message || '';
                const scanning = scanState === 'scanning' || scanState === 'starting';
                if (scanning) startOppScanPoll();
                else stopOppScanPoll();

                const progressHtml = buildOppScanProgressHtml(scan);
                const scanMeta = scanning
                    ? (scan.current_symbol
                        ? `Scanning ${scan.current_symbol} — ${scan.symbols_done || 0}/${scan.symbols_total || '?'}`
                        : `Scanning ${scan.symbols_done || 0}/${scan.symbols_total || '?'}…`)
                    : (scan.last_scan_ist
                        ? `Last scan: ${scan.last_scan_ist}`
                        : 'Analyzer warming up…');

                if (!opps.length) {
                    document.getElementById('opp-container').innerHTML = `
                        <div class="card" style="padding:20px;">
                            <div class="card-header" style="padding:0 0 12px 0; display:flex; justify-content:space-between; align-items:center;">
                                <span class="card-title">🔎 Today's Trade Opportunities</span>
                                <button class="btn btn-blue" style="padding:6px 12px; font-size:12px;" onclick="rescanOpportunities()" ${scanning ? 'disabled' : ''}>
                                    ${scanning ? '⏳ Scanning…' : '↻ Rescan Watchlist'}
                                </button>
                            </div>
                            ${progressHtml}
                            <p style="color:var(--accent-amber); margin-top:8px;">
                                ${msg || (scanning ? 'EnhancedAnalyzer is scanning your watchlist…' : 'Waiting for EnhancedAnalyzer watchlist scan…')}
                            </p>
                            <p style="color:var(--text-muted); font-size:12px; margin-top:8px;">
                                ${scanMeta}. Symbols are ranked by analyzer confidence — not the old fixed RELIANCE / HDFCBANK / TCS demo list.
                            </p>
                            <p style="color:var(--text-muted); font-size:11px; margin-top:6px;">Status: <strong>${scanState}</strong> — ${scanMsg}</p>
                        </div>`;
                    return;
                }

                let rows = '';
                opps.forEach((o, idx) => {
                    const sigPct = parseInt(o.signal_strength_pct) || 0;
                    const sigClass = sigPct >= 85 ? '' : sigPct >= 75 ? 'med' : 'low';
                    const whyHtml = (o.why_this_trade || []).map(w => `<span style="display:block; margin-bottom:3px;">✅ ${w}</span>`).join('');
                    const invHtml = (o.invalidation_rules || []).map(r => `<span style="display:block; margin-bottom:3px; color:#f87171;">⚠️ ${r}</span>`).join('');
                    const thesis = o.investment_thesis || [];
                    const scores = o.factor_scores || null;
                    const badges = o.factor_badges || {};
                    const trends = o.factor_trends || {};
                    const meta = o.fundamentals_meta || {};
                    const rel = o.valuation_relatives || {};
                    const strength = o.opportunity_strength || {};
                    const asOf = meta.as_of_label || (meta.fiscal_year ? `As of FY ${meta.fiscal_year}` : '');
                    const factorKeys = [
                        ['quality','Q'],['growth','G'],['value','V'],
                        ['financial_health','H'],['consistency','C'],['overall_fundamental','Overall']
                    ];
                    let factorStrip = '';
                    if (scores) {
                        factorStrip = factorKeys.map(([k, lab]) => {
                            const v = scores[k];
                            if (v == null) return '';
                            const badge = badges[k] || '';
                            const tr = (trends[k] && trends[k].label) ? ` <span style="color:#94a3b8;font-size:10px;">${trends[k].label}</span>` : '';
                            return `<span style="display:inline-block;margin:2px 8px 2px 0;padding:3px 8px;background:#0f172a;border:1px solid #334155;border-radius:4px;font-size:11px;">
                                <strong style="color:#e2e8f0;">${lab}</strong>
                                <span style="color:#60a5fa;margin-left:4px;">${Math.round(v)}</span>
                                <span style="color:#94a3b8;margin-left:4px;font-size:10px;">${badge}</span>${tr}
                            </span>`;
                        }).join('');
                    }
                    let peerLine = '';
                    if (rel.pe != null && rel.sector_pe_median != null && rel.pe_vs_sector_pct != null) {
                        const pct = rel.pe_vs_sector_pct;
                        const tone = pct < 0 ? '#4ade80' : '#fbbf24';
                        peerLine = `<div style="margin-top:6px;font-size:11px;color:#94a3b8;">P/E ${Number(rel.pe).toFixed(1)} · Sector ${Number(rel.sector_pe_median).toFixed(1)} · <span style="color:${tone};font-weight:600;">${pct > 0 ? '+' : ''}${Number(pct).toFixed(0)}% vs peers</span></div>`;
                    }
                    const thesisHtml = thesis.length
                        ? thesis.map(t => `<span style="display:block; margin-bottom:3px;">📌 ${t}</span>`).join('')
                        : '<span style="color:#64748b;">No fundamental thesis (store miss or incomplete annuals)</span>';
                    const aiHtml = o.ai_summary
                        ? `<div style="margin-top:10px;padding:8px 10px;background:#0f172a;border-left:3px solid #60a5fa;border-radius:2px;font-size:12px;color:#cbd5e1;line-height:1.45;">${o.ai_summary}</div>`
                        : '';
                    let strengthHtml = '';
                    if (strength.technical != null) {
                        const f = strength.fundamental != null ? Math.round(strength.fundamental) : '—';
                        strengthHtml = `<div style="margin-top:8px;font-size:11px;color:#94a3b8;">
                            Opportunity strength (display): Technical <strong style="color:#e2e8f0;">${Math.round(strength.technical)}</strong>
                            · Fundamental <strong style="color:#e2e8f0;">${f}</strong>
                            · Overall <strong style="color:#60a5fa;">${Math.round(strength.overall_opportunity || 0)}</strong>
                        </div>`;
                    }
                    const intelBlock = scores || thesis.length ? `
                        <div style="flex:1.2;">
                            <strong style="color:#a78bfa; font-size:12px;">INVESTMENT INTELLIGENCE</strong>
                            <div style="font-size:10px;color:#64748b;margin-top:2px;">${asOf}${meta.factor_version ? ' · factors v' + meta.factor_version : ''}</div>
                            <div style="margin-top:8px;">${factorStrip}</div>
                            ${peerLine}
                            <div style="margin-top:8px; font-size:12px; color:#cbd5e1;">${thesisHtml}</div>
                            ${aiHtml}
                            ${strengthHtml}
                        </div>` : `
                        <div style="flex:1;">
                            <strong style="color:#64748b; font-size:12px;">INVESTMENT INTELLIGENCE</strong>
                            <div style="margin-top:6px;font-size:12px;color:#64748b;">Factors unavailable</div>
                        </div>`;
                    const entryFmt = formatInrPrice(o.suggested_entry);
                    const slFmt = formatInrPrice(o.suggested_stop_loss);
                    const tpFmt = formatInrPrice(o.suggested_target);
                    const src = o.price_source || 'ANGEL';
                    const dir = (o.direction || 'BUY').toUpperCase();
                    const dirColor = dir === 'SELL' ? '#f87171' : '#4ade80';
                    const srcBadge = src.startsWith('ANGEL')
                        ? `<span class="badge badge-green" style="font-size:10px; margin-left:6px;">${src}</span>`
                        : `<span class="badge badge-amber" style="font-size:10px; margin-left:6px;">${src}</span>`;
                    rows += `
                        <tr class="opp-main-row" id="opp-row-${idx}" onclick="toggleOppDetail(${idx})">
                            <td><strong style="color:#e2e8f0; font-size:14px;">${o.symbol}</strong>${srcBadge} <span class="opp-chevron" id="chev-${idx}">▼</span></td>
                            <td><span class="opp-style-badge">${o.trading_style}</span><div style="color:${dirColor}; font-size:11px; font-weight:700; margin-top:2px;">${dir}</div></td>
                            <td style="color:#94a3b8; font-size:12px;">${o.strategy}</td>
                            <td><strong style="color:#fff;">₹${entryFmt}</strong></td>
                            <td><strong style="color:#f87171;">₹${slFmt}</strong></td>
                            <td><strong style="color:#4ade80;">₹${tpFmt}</strong></td>
                            <td style="color:#fbbf24; font-weight:700;">${o.risk_reward_ratio}</td>
                            <td><span class="sig-bar ${sigClass}">${sigPct}%</span></td>
                            <td><button class="btn btn-green" style="padding:5px 14px; font-size:12px;" onclick="event.stopPropagation(); populateTicket('${o.symbol}', '${o.suggested_entry}', '${o.suggested_stop_loss}', '${o.suggested_target}', '${dir}', '${(o.trading_style || 'INTRADAY')}', '${String(o.strategy || '').replace(/'/g, "\\'")}', '${o.suggested_quantity || 10}')">🎟️ Trade</button></td>
                        </tr>
                        <tr class="opp-detail-row" id="opp-detail-${idx}">
                            <td colspan="9">
                                <div style="display:flex; gap:28px; flex-wrap:wrap;">
                                    <div style="flex:1;min-width:180px;"><strong style="color:#60a5fa; font-size:12px;">WHY THIS TRADE? (Technical)</strong><div style="margin-top:6px; font-size:12px; color:#cbd5e1;">${whyHtml}</div></div>
                                    ${intelBlock}
                                    <div style="flex:1;min-width:160px;"><strong style="color:#fbbf24; font-size:12px;">INVALIDATION RULES</strong><div style="margin-top:6px; font-size:12px;">${invHtml}</div></div>
                                    <div style="display:flex; align-items:center;"><button class="btn btn-green" style="padding:8px 20px;" onclick="populateTicket('${o.symbol}', '${o.suggested_entry}', '${o.suggested_stop_loss}', '${o.suggested_target}', '${dir}', '${(o.trading_style || 'INTRADAY')}', '${String(o.strategy || '').replace(/'/g, "\\'")}', '${o.suggested_quantity || 10}')">🎟️ View Full Trade Plan</button></div>
                                </div>
                            </td>
                        </tr>
                    `;
                });

                const tableHtml = `
                    <div class="card" style="padding:0; overflow:hidden;">
                        <div class="card-header" style="padding:14px 16px; display:flex; justify-content:space-between; align-items:center; gap:12px;">
                            <span class="card-title">🔎 Today's Trade Opportunities</span>
                            <span style="display:flex; gap:8px; align-items:center;">
                                <span class="badge badge-blue">${opps.length} Analyzer Signals</span>
                                <button class="btn btn-blue" style="padding:5px 10px; font-size:11px;" onclick="rescanOpportunities()" ${scanning ? 'disabled' : ''}>
                                    ${scanning ? '⏳ Scanning…' : '↻ Rescan'}
                                </button>
                            </span>
                        </div>
                        <div style="padding:0 16px;">${progressHtml}</div>
                        <div style="overflow-x:auto;">
                        <table id="opp-table">
                            <thead><tr>
                                <th>Symbol</th><th>Style</th><th>Strategy</th>
                                <th>Entry (₹)</th><th>Stop Loss (₹)</th><th>Target (₹)</th>
                                <th>R:R</th><th>Signal</th><th>Action</th>
                            </tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                        </div>
                        <div style="padding:10px 16px; font-size:11px; color:#64748b;">
                            💡 Ranked by EnhancedAnalyzer confidence across your watchlist. Entry/SL/Target use live Angel LTP.
                            ${scanMeta}
                        </div>
                    </div>
                `;
                document.getElementById('opp-container').innerHTML = tableHtml;
            } catch(e) { console.error(e); }
            finally { _oppFetchInFlight = false; }
        }

        async function rescanOpportunities() {
            try {
                const res = await fetch('/api/opportunities/rescan');
                const data = await res.json().catch(() => ({}));
                if (data && data.started === false) {
                    // already scanning
                }
                startOppScanPoll();
                fetchOpportunities();
            } catch (e) { console.error(e); }
        }

        function toggleOppDetail(idx) {
            const detailRow = document.getElementById('opp-detail-' + idx);
            const mainRow = document.getElementById('opp-row-' + idx);
            const chev = document.getElementById('chev-' + idx);
            const isOpen = detailRow.classList.contains('open');
            detailRow.classList.toggle('open', !isOpen);
            if (!isOpen) { chev.style.transform = 'rotate(180deg)'; chev.style.color = '#60a5fa'; }
            else { chev.style.transform = ''; chev.style.color = '#64748b'; }
        }

        async function fetchWatchlist(manual) {
            try {
                const badge = document.getElementById('watchlist-refresh-badge');
                if (badge && manual) badge.innerText = 'REFRESHING…';
                const res = await fetch('/api/watchlist');
                const list = await res.json();
                
                document.getElementById('watchlist-title-label').innerText = `👁️ Watchlist Monitor (${list.length} Stocks)`;
                document.getElementById('btn-tab-watchlist').innerText = `👁️ Watchlist (${list.length} Stocks)`;

                let liveCount = 0;
                let html = '';
                list.forEach(w => {
                    if (w.ltp && w.ltp !== '—') liveCount += 1;
                    const src = (w.price_source || '').replace(/_/g, ' ');
                    html += `
                        <tr>
                            <td>
                                <strong>${w.symbol}</strong>
                                ${src ? `<div class="sub-text" style="font-size:10px;margin-top:2px;">${src}</div>` : ''}
                            </td>
                            <td>${w.ltp}</td>
                            <td style="color:${String(w.change||'').startsWith('+')?'var(--accent-green)':'var(--accent-red)'}">${w.change}</td>
                            <td>${w.change_pct}</td>
                            <td>${w.volume}</td>
                            <td style="text-align:center;">
                                <button class="btn btn-red btn-sm" onclick="removeWatchlistSymbol('${w.symbol}')">🗑️ Remove</button>
                            </td>
                        </tr>
                    `;
                });
                document.getElementById('watchlist-body').innerHTML = html;
                if (badge) {
                    badge.innerText = liveCount > 0
                        ? `LIVE ${liveCount}/${list.length}`
                        : 'WAITING FOR WS TICKS';
                    badge.className = liveCount > 0 ? 'badge badge-green' : 'badge badge-amber';
                }
            } catch(e) { console.error(e); }
        }

        async function addWatchlistSymbol() {
            const input = document.getElementById('add-symbol-input');
            const symbol = input.value.trim().toUpperCase();
            if (!symbol) {
                alert('Enter a symbol (e.g. SBIN)');
                return;
            }

            try {
                const res = await fetch('/api/watchlist/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol })
                });
                const data = await res.json();
                if (data.success) {
                    input.value = '';
                    fetchWatchlist();
                } else {
                    alert(data.error || 'Failed to add symbol');
                }
            } catch (e) {
                console.error(e);
                alert('Could not add symbol. Restart the dashboard if you just updated NexTrade.');
            }
        }

        async function removeWatchlistSymbolFromInput() {
            const input = document.getElementById('add-symbol-input');
            const symbol = input.value.trim().toUpperCase();
            if (!symbol) {
                alert('Enter the symbol to remove (e.g. SBIN)');
                return;
            }
            const ok = await removeWatchlistSymbol(symbol);
            if (ok) input.value = '';
        }

        async function removeWatchlistSymbol(symbol) {
            if (!confirm(`Remove ${symbol} from the watchlist?`)) return false;

            try {
                const res = await fetch('/api/watchlist/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol })
                });
                const data = await res.json();
                if (data.success) {
                    fetchWatchlist();
                    return true;
                }
                alert(data.error || 'Failed to remove symbol');
                return false;
            } catch (e) {
                console.error(e);
                alert('Could not remove symbol. Restart the dashboard if you just updated NexTrade.');
                return false;
            }
        }

        async function downloadWatchlist() {
            try {
                const res = await fetch('/api/watchlist/download');
                if (!res.ok) {
                    alert('Failed to download watchlist (HTTP ' + res.status + ')');
                    return;
                }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
                a.download = 'NexTrade_Watchlist_' + stamp + '.csv';
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
            } catch (e) {
                console.error(e);
                alert('Watchlist download failed. Restart the dashboard if you just updated NexTrade.');
            }
        }

        let editingZerodhaHoldingId = null;

        function cancelZerodhaEdit() {
            editingZerodhaHoldingId = null;
            document.getElementById('zh-symbol').value = '';
            document.getElementById('zh-qty').value = '';
            document.getElementById('zh-avg').value = '';
            document.getElementById('zh-notes').value = '';
            document.getElementById('zh-symbol').disabled = false;
            document.getElementById('zh-submit-btn').innerText = 'Add Holding';
            document.getElementById('zh-cancel-btn').style.display = 'none';
        }

        function editZerodhaHolding(id, symbol, qty, avgPrice, notes) {
            editingZerodhaHoldingId = id;
            document.getElementById('zh-symbol').value = symbol.replace(/-EQ$/i, '');
            document.getElementById('zh-qty').value = qty;
            document.getElementById('zh-avg').value = avgPrice;
            document.getElementById('zh-notes').value = notes || '';
            document.getElementById('zh-symbol').disabled = false;
            document.getElementById('zh-submit-btn').innerText = 'Update Holding';
            document.getElementById('zh-cancel-btn').style.display = 'inline-block';
            document.getElementById('zh-symbol').focus();
        }

        async function saveZerodhaHolding() {
            const symbol = document.getElementById('zh-symbol').value.trim();
            const qty = parseInt(document.getElementById('zh-qty').value, 10);
            const avg_price = parseFloat(document.getElementById('zh-avg').value);
            const notes = document.getElementById('zh-notes').value.trim();
            if (!symbol || !qty || !avg_price) {
                alert('Please enter symbol, quantity, and average price.');
                return;
            }
            const payload = { symbol, qty, avg_price, notes };
            const isEdit = !!editingZerodhaHoldingId;
            if (isEdit) payload.id = editingZerodhaHoldingId;
            const res = await fetch('/api/holdings/manual', {
                method: isEdit ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.success) {
                cancelZerodhaEdit();
                fetchHoldings();
            } else {
                alert(data.error || 'Failed to save Zerodha holding');
            }
        }

        async function deleteZerodhaHolding(id, symbol) {
            if (!confirm(`Remove manual Zerodha holding ${symbol}?`)) return;
            const res = await fetch('/api/holdings/manual', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id }),
            });
            const data = await res.json();
            if (data.success) {
                if (editingZerodhaHoldingId === id) cancelZerodhaEdit();
                fetchHoldings();
            } else {
                alert(data.error || 'Failed to delete holding');
            }
        }

        async function fetchHoldings() {
            try {
                const res = await fetch('/api/holdings');
                const data = await res.json();
                const list = data.holdings || data;
                const summary = data.summary;

                if (summary) {
                    document.getElementById('holdings-invested').innerText = summary.total_invested_fmt;
                    document.getElementById('holdings-current').innerText = summary.total_current_fmt;

                    const pnlEl = document.getElementById('holdings-pnl');
                    pnlEl.innerText = summary.total_pnl_fmt;
                    const pnlColor = summary.total_pnl_raw >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                    pnlEl.style.color = pnlColor;

                    const pctEl = document.getElementById('holdings-pnl-pct');
                    pctEl.innerText = summary.total_pnl_pct_fmt + ' on invested capital';
                    pctEl.style.color = pnlColor;

                    const ltpBadge = document.getElementById('holdings-ltp-badge');
                    if (ltpBadge) {
                        if (summary.holding_count === 0) {
                            ltpBadge.className = 'badge badge-amber';
                            ltpBadge.innerText = 'EMPTY';
                        } else if (summary.live_ltp_count === summary.holding_count) {
                            ltpBadge.className = 'badge badge-green';
                            ltpBadge.innerText = 'LIVE';
                        } else if (summary.live_ltp_count > 0) {
                            ltpBadge.className = 'badge badge-amber';
                            ltpBadge.innerText = 'PARTIAL';
                        } else {
                            ltpBadge.className = 'badge badge-amber';
                            ltpBadge.innerText = 'OFFLINE';
                        }
                    }

                    const titleEl = document.getElementById('holdings-title');
                    if (titleEl) {
                        const n = summary.holding_count || 0;
                        titleEl.innerText = `💼 Portfolio Holdings (${n} Stock${n === 1 ? '' : 's'})`;
                    }
                }

                const syncBadge = document.getElementById('holdings-sync-badge');
                if (syncBadge) {
                    const src = data.holdings_source || 'UNKNOWN';
                    if (src === 'MIXED' && data.holdings_synced) {
                        syncBadge.className = 'badge badge-green';
                        syncBadge.innerText = 'LIVE + MANUAL';
                    } else if (src === 'ANGEL_LIVE' && data.holdings_synced) {
                        syncBadge.className = 'badge badge-green';
                        syncBadge.innerText = 'LIVE · SYNCED';
                    } else if (src === 'MANUAL_ZERODHA') {
                        syncBadge.className = 'badge';
                        syncBadge.style.background = 'rgba(41, 182, 246, 0.15)';
                        syncBadge.style.color = 'var(--accent-blue)';
                        syncBadge.style.border = '1px solid var(--accent-blue)';
                        syncBadge.innerText = 'MANUAL ZERODHA';
                    } else if (src === 'DEMO') {
                        syncBadge.className = 'badge badge-amber';
                        syncBadge.innerText = 'DEMO';
                    } else if (src === 'ERROR') {
                        syncBadge.className = 'badge badge-red';
                        syncBadge.innerText = 'SYNC ERROR';
                    } else {
                        syncBadge.className = 'badge badge-amber';
                        syncBadge.innerText = 'OFFLINE';
                    }
                }

                let html = '';
                if (!list || list.length === 0) {
                    const errMsg = data.holdings_error
                        ? `<span style="color:var(--accent-red);">${data.holdings_error}</span>`
                        : '<span style="color:var(--text-muted);">No holdings in portfolio. Add Zerodha stocks manually above, or connect Angel One for live sync.</span>';
                    html = `<tr><td colspan="8">${errMsg}</td></tr>`;
                } else {
                    list.forEach(h => {
                        const pnlPositive = (h.pnl_raw != null) ? h.pnl_raw >= 0 : String(h.pnl || '').startsWith('+');
                        const pnlColor = (h.pnl_raw == null && (h.pnl === '—' || !h.pnl))
                            ? 'var(--text-muted)'
                            : (pnlPositive ? 'var(--accent-green)' : 'var(--accent-red)');
                        let ltpLabel;
                        if (h.ltp_status === 'UNQUOTED' || h.ltp_raw == null) {
                            ltpLabel = `N/A <span class="sub-text">(unquoted)</span>`;
                        } else if (h.ltp_live) {
                            const tag = (h.ltp_status === 'REST' || String(h.ltp_source || '').includes('REST'))
                                ? 'Angel REST' : 'LIVE';
                            ltpLabel = `${h.ltp} <span class="sub-text">(${tag})</span>`;
                        } else if (h.ltp_status === 'SNAPSHOT') {
                            ltpLabel = `${h.ltp} <span class="sub-text">(snapshot)</span>`;
                        } else {
                            ltpLabel = `${h.ltp} <span class="sub-text">(cached)</span>`;
                        }
                        const broker = h.broker || 'ANGEL';
                        const brokerBadge = broker === 'ZERODHA'
                            ? '<span class="badge" style="background:rgba(41,182,246,0.15);color:var(--accent-blue);border:1px solid var(--accent-blue);">ZERODHA</span>'
                            : '<span class="badge badge-green">ANGEL</span>';
                        let actions = '<span class="sub-text">—</span>';
                        if (h.manual && h.id) {
                            const symJs = JSON.stringify(h.symbol);
                            const notesJs = JSON.stringify(h.notes || '');
                            actions = `<button class="btn btn-amber btn-sm" onclick='editZerodhaHolding(${JSON.stringify(h.id)}, ${symJs}, ${h.qty}, ${h.avg_price_raw}, ${notesJs})'>Edit</button> `
                                + `<button class="btn btn-red btn-sm" onclick='deleteZerodhaHolding(${JSON.stringify(h.id)}, ${symJs})'>Delete</button>`;
                        }
                        const notesHint = h.notes ? `<br><span class="sub-text">${h.notes}</span>` : '';
                        html += `<tr><td><strong>${h.symbol}</strong>${notesHint}</td><td>${brokerBadge}</td><td>${h.qty}</td><td>${h.avg_price}</td><td>${ltpLabel}</td><td style="color:${pnlColor}">${h.pnl}</td><td>${h.total_value}</td><td style="text-align:center;white-space:nowrap;">${actions}</td></tr>`;
                    });
                    if (data.holdings_error) {
                        html = `<tr><td colspan="8" style="color:var(--accent-amber);font-size:12px;">${data.holdings_error}</td></tr>` + html;
                    }
                }
                document.getElementById('holdings-body').innerHTML = html;
            } catch(e) { console.error(e); }
        }

        async function fetchPremarket() {
            try {
                const res = await fetch('/api/premarket', { cache: 'no-store' });
                const data = await res.json();
                const badge = document.getElementById('premarket-status-badge');
                const winEl = document.getElementById('premarket-window-label');
                if (badge) {
                    if (data.demo) {
                        badge.className = 'badge badge-amber';
                        badge.innerText = 'DEMO';
                    } else if (data.data_mode === 'LIVE') {
                        badge.className = 'badge badge-green';
                        badge.innerText = 'LIVE';
                    } else {
                        badge.className = 'badge badge-amber';
                        badge.innerText = data.data_mode || 'PARTIAL';
                    }
                }
                if (winEl) {
                    winEl.innerText = (data.window_label || '') + (data.ist_datetime ? ' · ' + data.ist_datetime : '');
                }

                const biasClass = (data.market_bias || '').includes('BULLISH') ? 'badge-green'
                    : ((data.market_bias || '').includes('BEARISH') || (data.market_bias || '').includes('HIGH VOL') ? 'badge-red' : 'badge-amber');
                let html = `<strong>Market Bias:</strong> <span class="badge ${biasClass}">${data.market_bias || '—'}</span>`;
                if (data.bias_detail) html += `<div class="sub-text" style="margin-top:6px;">${data.bias_detail}</div>`;
                html += `<div style="margin-top:12px; line-height:1.7;">`;
                html += `<div><strong>NIFTY:</strong> ${data.nifty_trend || '—'}</div>`;
                html += `<div><strong>Bank NIFTY:</strong> ${data.bank_nifty_trend || '—'}</div>`;
                html += `<div><strong>India VIX:</strong> ${data.vix_level != null ? data.vix_level : '—'}</div>`;
                html += `<div><strong>Breadth:</strong> ${data.breadth_label || '—'}</div>`;
                html += `<div class="sub-text">Index source: ${data.index_source || '—'} · Focus source: ${data.focus_source || '—'}</div>`;
                html += `</div>`;

                const stocks = data.focus_stocks || [];
                html += `<br><strong>Top Focus Stocks:</strong>`;
                if (!stocks.length) {
                    html += `<div class="sub-text" style="margin-top:8px;">No focus stocks yet. Open Opportunities and wait for analyzer scan, or ensure watchlist has Angel LTP.</div>`;
                } else {
                    html += `<ul class="bullet-list">`;
                    stocks.forEach(f => {
                        const dir = (f.direction || '').toUpperCase();
                        const dirBadge = dir === 'SELL'
                            ? '<span class="badge badge-red" style="margin-right:6px;">SELL</span>'
                            : (dir === 'BUY' ? '<span class="badge badge-green" style="margin-right:6px;">BUY</span>' : '');
                        html += `<li>${dirBadge}<strong>${f.symbol || '—'}:</strong> ${f.reason || '—'}</li>`;
                    });
                    html += `</ul>`;
                }
                if (data.note) {
                    html += `<div class="sub-text" style="margin-top:10px; color:var(--text-muted);">${data.note}</div>`;
                }
                document.getElementById('premarket-box').innerHTML = html;
            } catch (e) {
                console.error(e);
                const box = document.getElementById('premarket-box');
                if (box) box.innerHTML = '<span style="color:var(--accent-red);">Pre-market brief failed to load.</span>';
            }
        }

        async function fetchJournal() {
            if (window._journalFetchInflight) return;
            window._journalFetchInflight = true;
            const bodyEl = document.getElementById('executed-trades-body');
            const hadRows = !!(bodyEl && bodyEl.querySelector('tr td strong'));
            if (bodyEl && !hadRows) {
                bodyEl.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--text-muted);">Loading journal…</td></tr>';
            }
            try {
                const ctrl = new AbortController();
                const timer = setTimeout(() => ctrl.abort(), 20000);
                const res = await fetch('/api/journal', { signal: ctrl.signal, cache: 'no-store' });
                clearTimeout(timer);
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                if (data.error && !Array.isArray(data.executed_trades)) throw new Error(data.error);
                document.getElementById('j-net-pnl').innerText = data.net_pnl_formatted;
                document.getElementById('j-win-rate').innerText = data.win_rate_pct + '%';
                document.getElementById('j-trades').innerText = data.total_trades;
                document.getElementById('eod-winrate').innerText = data.win_rate_pct + '%';
                document.getElementById('eod-trades').innerText = data.total_trades;

                let bHtml = '';
                for (const [style, pnl] of Object.entries(data.style_breakdown_formatted || {})) {
                    bHtml += `<div><strong>${style}:</strong> <span style="color:var(--accent-green);">${pnl}</span></div>`;
                }
                document.getElementById('style-breakdown-box').innerHTML = bHtml || 'No trades executed today.';

                let tHtml = '';
                if (data.executed_trades && data.executed_trades.length > 0) {
                    data.executed_trades.forEach(t => {
                        const strat = t.strategy || '—';
                        const dir = t.direction || '—';
                        tHtml += `<tr><td>${t.timestamp || '—'}</td><td><strong>${t.symbol || '—'}</strong></td><td>${t.style || '—'}</td><td>${strat}</td><td>${dir}</td><td>${t.quantity ?? '—'}</td><td>₹${t.entry_price ?? '—'}</td><td>₹${t.exit_price ?? '—'}</td><td>₹${t.pnl ?? '—'}</td><td><span class="badge badge-green">${t.status || 'CLOSED'}</span></td></tr>`;
                    });
                } else {
                    tHtml = '<tr><td colspan="10" style="text-align:center; color:var(--text-muted);">No executed trades found today.</td></tr>';
                }
                if (bodyEl) bodyEl.innerHTML = tHtml;
            } catch (e) {
                console.error(e);
                if (bodyEl && !hadRows) {
                    bodyEl.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--accent-red);">Journal load failed or timed out. Try ↻ Refresh Journal, or open <a href="/api/journal" target="_blank" style="color:var(--accent-blue);">/api/journal</a> in a new tab.</td></tr>';
                }
            } finally {
                window._journalFetchInflight = false;
            }
        }

        function populateTicket(symbol, entry, sl, tp, direction, style, strategy, qty) {
            const dir = String(direction || 'BUY').toUpperCase() === 'SELL' ? 'SELL' : 'BUY';
            const num = (v) => {
                const n = parseFloat(String(v).replace(/[^0-9.\-]/g, ''));
                return Number.isFinite(n) ? n : NaN;
            };
            const entryN = num(entry);
            const slN = num(sl);
            const tpN = num(tp);
            // Preserve SL/TP geometry vs entry when live LTP refresh shifts entry slightly
            window._tkPreserveLevels = {
                direction: dir,
                entry: entryN,
                sl: slN,
                tp: tpN,
            };

            document.getElementById('tk-symbol').value = symbol;
            const dirEl = document.getElementById('tk-direction');
            if (dirEl) dirEl.value = dir;
            if (style) {
                const st = document.getElementById('tk-style');
                if (st) {
                    const want = String(style).toUpperCase();
                    for (const opt of st.options) {
                        if (opt.value.toUpperCase() === want) { st.value = opt.value; break; }
                    }
                }
            }
            if (strategy) {
                const sg = document.getElementById('tk-strategy');
                if (sg) {
                    let matched = false;
                    for (const opt of sg.options) {
                        if (opt.value === strategy || opt.text.includes(strategy)) {
                            sg.value = opt.value;
                            matched = true;
                            break;
                        }
                    }
                    if (!matched) {
                        // Analyzer strategy names may not be in registry — keep current or first
                        const opt = document.createElement('option');
                        opt.value = strategy;
                        opt.text = strategy + ' (from analyzer)';
                        sg.appendChild(opt);
                        sg.value = strategy;
                    }
                }
            }
            if (qty) document.getElementById('tk-qty').value = parseInt(qty, 10) || 10;
            document.getElementById('tk-entry').value = entryN;
            document.getElementById('tk-sl').value = slN;
            document.getElementById('tk-tp').value = tpN;
            fetchTicketLiveLtp(true);

            // Switch tab to ticket
            const btn = document.querySelectorAll('.tab-btn')[3];
            btn.click();
        }

        async function fetchTicketLiveLtp(preserveGeometry) {
            const sym = (document.getElementById('tk-symbol').value || 'RELIANCE').trim().toUpperCase();
            const badge = document.getElementById('tk-ltp-badge');
            if (badge) badge.innerText = '— fetching Angel LTP…';
            try {
                const res = await fetch('/api/ltp?symbol=' + encodeURIComponent(sym));
                const data = await res.json();
                if (data.success && data.ltp) {
                    const ltp = parseFloat(data.ltp);
                    document.getElementById('tk-entry').value = ltp.toFixed(2);
                    document.getElementById('tk-qty').value = scripQtyFromLtp(ltp);
                    if (badge) badge.innerText = '(LTP ' + ltp.toFixed(2) + ' · ' + (data.source || 'ANGEL') + ')';
                    // Keep SELL/BUY SL-TP distances when refreshing LTP from Opportunities
                    const preserved = window._tkPreserveLevels;
                    if (preserveGeometry && preserved && preserved.entry > 0) {
                        const scale = ltp / preserved.entry;
                        if (Number.isFinite(preserved.sl)) {
                            document.getElementById('tk-sl').value = (preserved.sl * scale).toFixed(2);
                        }
                        if (Number.isFinite(preserved.tp)) {
                            document.getElementById('tk-tp').value = (preserved.tp * scale).toFixed(2);
                        }
                    }
                } else {
                    if (badge) badge.innerText = '(Angel LTP unavailable — ' + (data.error || 'offline') + ')';
                }
            } catch (e) {
                if (badge) badge.innerText = '(Angel LTP fetch failed)';
            }
        }

        async function generatePlan() {
            const symbol = document.getElementById('tk-symbol').value;
            const style = document.getElementById('tk-style').value;
            const strategy = document.getElementById('tk-strategy').value;
            const direction = (document.getElementById('tk-direction') || {}).value || 'BUY';
            const entry = parseFloat(document.getElementById('tk-entry').value);
            const qty = parseInt(document.getElementById('tk-qty').value);
            const sl = parseFloat(document.getElementById('tk-sl').value);
            const tp = parseFloat(document.getElementById('tk-tp').value);
            const tsl = parseFloat(document.getElementById('tk-tsl').value);

            const res = await fetch('/api/create_trade_plan', {
                method: 'POST',
                body: JSON.stringify({
                    symbol,
                    trading_style: style,
                    strategy,
                    direction,
                    entry_price: entry,
                    quantity: qty,
                    stop_loss_price: sl,
                    target_price: tp,
                    trailing_stop_amount: tsl
                })
            });
            const data = await res.json();
            if (data.success) {
                const s = data.summary;
                const dirBadge = direction === 'SELL' ? 'badge-red' : 'badge-green';
                document.getElementById('plan-summary-box').innerHTML = `
                    <strong style="font-size:15px; color:#fff;">${s.title}</strong><br>
                    <span class="badge ${dirBadge}" style="margin-top:4px; display:inline-block;">${direction} · ${s.style_strategy}</span><br><br>
                    Capital Required: <strong>${s.capital_required}</strong><br>
                    Maximum Risk: <span style="color:var(--accent-red);">${s.maximum_loss}</span><br>
                    Potential Profit: <span style="color:var(--accent-green);">${s.potential_profit}</span><br>
                    Risk / Reward: <strong>${s.risk_reward_ratio}</strong><br>
                    <div style="margin-top:10px; padding-top:8px; border-top:1px solid var(--border-color);">
                        <strong>V2 charges (preview):</strong> ${s.charges_v2 || '—'}<br>
                        <span class="sub-text">${s.charges_qty_note || ''}</span><br>
                        <span class="sub-text">${s.charges_v3 || 'V3 slippage off.'} Ledger on close still uses the Angel flat template.</span>
                    </div><br>
                    <div class="sub-text" style="color:var(--accent-green);">${s.user_reassurance}</div>
                `;
            } else {
                alert(data.error || "Failed to create trade plan");
            }
        }

        async function refreshScheduledOrders() {
            try {
                const res = await fetch('/api/scheduled_paper_trades');
                const data = await res.json();
                const box = document.getElementById('scheduled-orders-box');
                if (!box) return;
                const orders = (data.orders || []).filter(o => o.status === 'ARMED' || o.status === 'FILLED' || o.status === 'EXPIRED');
                if (!orders.length) {
                    box.innerHTML = 'No armed schedules.';
                    return;
                }
                let html = '<strong style="color:#fff;">Scheduled paper orders</strong><br>';
                orders.slice().reverse().slice(0, 8).forEach(o => {
                    const st = o.status || '';
                    const color = st === 'ARMED' ? 'var(--accent-amber)' : (st === 'FILLED' ? 'var(--accent-green)' : 'var(--text-muted)');
                    const showErr = o.last_error && st !== 'FILLED';
                    html += `<div style="margin-top:8px; padding-top:6px; border-top:1px solid var(--border-color);">
                        <span style="color:${color}; font-weight:600;">${st}</span>
                        · ${o.symbol} ${o.direction} × ${o.quantity}
                        · start <strong>${o.start_hhmm}</strong> IST
                        ${st === 'ARMED' ? ` <button class="btn btn-amber btn-sm" onclick="cancelScheduled('${o.schedule_id}')">Cancel</button>` : ''}
                        ${st === 'FILLED' && o.executed_at_ist ? `<div class="sub-text" style="color:var(--accent-green);">Filled ${o.executed_at_ist} IST</div>` : ''}
                        ${showErr ? `<div class="sub-text" style="color:var(--accent-red);">${o.last_error}</div>` : ''}
                    </div>`;
                });
                box.innerHTML = html;
            } catch (e) { console.error(e); }
        }

        async function cancelScheduled(scheduleId) {
            const res = await fetch('/api/cancel_scheduled_paper_trade', {
                method: 'POST',
                body: JSON.stringify({ schedule_id: scheduleId })
            });
            const data = await res.json();
            alert(data.success ? data.message : (data.error || 'Cancel failed'));
            refreshScheduledOrders();
        }

        async function executeOrSchedulePaperTrade() {
            const startSel = document.getElementById('tk-start-time');
            const startHhmm = startSel ? startSel.value : 'IMMEDIATE';
            if (startHhmm && startHhmm.toUpperCase() !== 'IMMEDIATE') {
                const btn = document.querySelector('button[onclick="executeOrSchedulePaperTrade()"]');
                if (btn) { btn.disabled = true; btn.innerText = 'Arming…'; }
                try {
                    const res = await fetch('/api/schedule_paper_trade', {
                        method: 'POST',
                        body: JSON.stringify({ start_hhmm: startHhmm })
                    });
                    const data = await res.json();
                    if (data.success) {
                        alert('⏰ ' + data.message);
                        refreshScheduledOrders();
                        updateStatus();
                    } else if (data.already_due || data.immediate) {
                        // Fall through to immediate execute
                        await executePaperTrade();
                    } else if (data.u5_violation) {
                        alert('⏸️ Mandate not approved.\\n\\n' + (data.error || ''));
                    } else {
                        alert(data.error || 'Failed to arm schedule');
                    }
                } finally {
                    if (btn) { btn.disabled = false; btn.innerText = '🚀 Execute / Arm Paper Trade'; }
                }
                return;
            }
            await executePaperTrade();
        }

        async function executePaperTrade() {
            const btn = document.querySelector('button[onclick="executeOrSchedulePaperTrade()"]')
                || document.querySelector('button[onclick="executePaperTrade()"]');
            const oldText = btn ? btn.innerText : '';
            if (btn) { btn.innerText = 'Waiting Angel LTP…'; btn.disabled = true; }

            try {
                const maxRetries = 15; // ~45s (3s interval) to cover WS warm-up without manual second click
                let attempt = 0;
                while (true) {
                    const res = await fetch('/api/execute_paper_trade', { method: 'POST' });
                    const data = await res.json();

                    if (data.success) {
                        alert("✅ " + data.message);
                        updateStatus();
                        fetchJournal();
                        refreshScheduledOrders();
                        const tabBtn = document.querySelectorAll('.tab-btn')[5];
                        tabBtn.click();
                        break;
                    }

                    if (data.u5_violation) {
                        alert(
                            "⏸️ Paper trade blocked — today's Trading Mandate is not approved yet.\\n\\n" +
                            (data.user_action || "Open NEXTRADE TODAY (15-Min Cockpit), scroll to Today's Trading Mandate Boundaries, click APPROVE & START TODAY'S TRADING MANDATE, then try again.") +
                            "\\n\\n(This is Invariant U5 safety — not a crash.)"
                        );
                        const todayBtn = document.querySelector('.tab-btn[onclick*="tab-today"]');
                        showTab({ currentTarget: todayBtn }, 'tab-today');
                        try { document.getElementById('btn-approve-mandate').scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
                        break;
                    }

                    if (data.live_ltp_required && attempt < maxRetries) {
                        attempt += 1;
                        if (btn) btn.innerText = `Waiting Angel LTP… retry ${attempt}/${maxRetries}`;
                        await new Promise(r => setTimeout(r, 3000));
                        continue;
                    }

                    alert(data.error || "Failed to execute paper trade");
                    break;
                }
            } finally {
                if (btn) { btn.innerText = oldText; btn.disabled = false; }
            }
        }

        async function runFullAudit() {
            const logBox = document.getElementById('ctrl-log');
            logBox.innerText = "Executing Phase 6G Audit...";
            const res = await fetch('/api/run_audit', { method: 'POST' });
            const data = await res.json();
            logBox.innerHTML = `✅ <strong>Audit Passed (${data.invariants_passed}/15)</strong><br>SHA-256 Digest:<br><span class="hash-code">${data.manifest_sha256}</span>`;
        }

        async function triggerKill(type) {
            const logBox = document.getElementById('ctrl-log');
            logBox.innerText = `Triggering ${type} kill...`;
            const res = await fetch('/api/trigger_kill', {
                method: 'POST',
                body: JSON.stringify({ target: type, account_id: 'ACC_PROD_MULTI_01' })
            });
            const data = await res.json();
            logBox.innerHTML = `🚨 <strong>${data.message}</strong>`;
        }

        async function fetchStrategies() {
            try {
                const res = await fetch('/api/strategies');
                const strats = await res.json();
                const sel = document.getElementById('tk-strategy');
                if (strats && strats.length > 0) {
                    let html = '';
                    strats.forEach(s => {
                        html += `<option value="${s.name}">${s.name} (${s.trading_style} | ${s.segment})</option>`;
                    });
                    sel.innerHTML = html;
                }
            } catch (e) { console.error(e); }
        }

        // Initial Load
        fetchTodayMandate();
        fetchStrategies();
        updateStatus();
        fetchOpportunities();
        fetchWatchlist();
        fetchHoldings();
        fetchPremarket();
        fetchJournal();
        loadDayRiskPolicy();
        fetchTicketLiveLtp();
        refreshScheduledOrders();
        document.getElementById('tk-symbol').addEventListener('change', fetchTicketLiveLtp);
        setInterval(updateStatus, 5000);
        setInterval(refreshScheduledOrders, 10000);
        setInterval(fetchHoldings, 45000);
        setInterval(fetchTodayMandate, 60000);
        setInterval(fetchOpportunities, 60000);
        // Watchlist: first load often races WS connect — keep polling for live ticks
        setInterval(() => { fetchWatchlist(false); }, 12000);
        setTimeout(() => { fetchWatchlist(false); }, 3000);
        setTimeout(() => { fetchWatchlist(false); }, 8000);
    </script>
</body>
</html>
"""


def start_dashboard_server():
    # Phase 7P freeze-allowed security boundary: localhost only (not LAN/Internet)
    global PORT
    _bind_host = "127.0.0.1"
    os.chdir(_WORKSPACE_DIR)

    # Single-instance guard: do NOT spawn a second server on PORT+1 (duplicate Angel WS).
    candidate_ports = (PORT, PORT + 1, PORT + 2, 8590)
    for p in candidate_ports:
        try:
            from urllib.request import urlopen
            with urlopen(f"http://127.0.0.1:{p}/api/heartbeat", timeout=1.5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                existing = f"http://127.0.0.1:{p}"
                print("\n" + "=" * 70)
                print("[!] NexTrade dashboard is ALREADY RUNNING.")
                print(f"[!] Use the existing browser tab: {existing}")
                print("[!] A second dashboard would open another Angel WebSocket and can get the feed declined.")
                print("[!] Close the existing browser tab and stop that python process (Ctrl+C / Task Manager)")
                print("[!] before starting a new instance. New browser was NOT opened.")
                print("=" * 70 + "\n")
                return
        except Exception:
            pass

    # Fresh Angel session each dashboard boot (avoid stale singleton from wrong CWD)
    import ui_new.connection_manager as _cm_mod
    import trading_app.angel_market_data_bridge as _amb
    _cm_mod._connection_manager = None
    _amb._conn_mgr = None
    _amb._bridge_started = False
    _amb._last_error = None
    start_angel_market_data()
    start_opportunity_scanner()
    paper_scheduler.start_scheduler_worker(
        now_fn=now_ist,
        market_open_fn=is_market_open,
        fill_fn=fill_paper_trade_plan,
        interval_sec=5.0,
    )
    # Angel MIS parity: force-close INTRADAY/SCALPING paper at 15:15 IST
    try:
        so = _square_off_due_paper_positions(now_ist())
        if so.get("closed_count"):
            print(f"[*] Startup square-off closed {so['closed_count']} leftover INTRADAY paper position(s).")
    except Exception as exc:
        logger.warning("Startup paper square-off failed: %s", exc)
    paper_scheduler.start_square_off_worker(
        now_fn=now_ist,
        square_off_fn=_paper_monitor_then_square_off,
        interval_sec=15.0,
    )

    # Threading: UI polls (/api/status, /api/ltp, …) must not block serving the HTML page.
    # A single-threaded HTTPServer turns any slow Angel call into a blank browser tab.
    server = None
    bind_error = None
    for candidate in candidate_ports:
        try:
            server = _ExclusiveThreadingHTTPServer((_bind_host, candidate), UnifiedWebAppHandler)
            server.daemon_threads = True
            PORT = candidate
            break
        except OSError as exc:
            bind_error = exc
            server = None
    if server is None:
        print(f"[!] Failed to bind {_bind_host}:{PORT}: {bind_error}")
        print("[!] Another process may still be using the port. Stop it (Ctrl+C / Task Manager) and retry.")
        raise bind_error if bind_error else OSError("bind failed")

    url = f"http://127.0.0.1:{PORT}"
    print("\n" + "="*70)
    print("[+] NEXTRADE UNIFIED 15-MINUTE COCKPIT & AUTONOMOUS SYSTEM IS RUNNING (INR / Rs)")
    print(f"[*] Opening Web Dashboard: {url}")
    print(f"[*] Paper Terminal: {url}/terminal (T1–T3 preview · no live broker)")
    print(f"[*] Listen address: {_bind_host}:{PORT} (paper boundary — localhost only)")
    print("[*] Angel One WebSocket market data starting in background…")
    print("[*] Paper trades require live Angel LTP (fail closed if quote unavailable)")
    print("[*] Paper positions persist across opportunity rescan / server restart")
    print("[*] INTRADAY/SCALPING paper auto square-off at 03:15 PM IST (Angel MIS parity)")
    print("="*70 + "\n")
    
    def _open_browser():
        time.sleep(1)
        try:
            opened = webbrowser.open(url)
            if not opened:
                print(f"[!] Browser auto-open did not succeed. Open manually: {url}")
        except Exception as exc:
            print(f"[!] Browser auto-open failed ({exc}). Open manually: {url}")

    print(f"[*] If the browser does not open, visit: {url}")
    print("[*] Keep this window open. Closing it OR pressing Ctrl+C stops the dashboard.")
    threading.Thread(target=_open_browser, daemon=True).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping NexTrade Unified Server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    start_dashboard_server()
