"""
Paper trade start-time scheduler + intraday square-off (IST).

Arms a validated TradePlan to fire at 09:15 / 09:30 / 10:00 … same day.
Fill still requires market-open + Angel WS LTP (OIE-001). Does not change risk limits.

Also hosts Angel MIS-parity square-off at 15:15 IST for INTRADAY/SCALPING paper.
"""

from __future__ import annotations

import logging
import threading
import uuid
from copy import deepcopy
from datetime import datetime, time as dt_time, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("PaperTradeScheduler")

# Preset strategy start slots (IST)
PRESET_START_SLOTS = (
    "09:15",
    "09:30",
    "09:45",
    "10:00",
    "10:15",
    "10:30",
    "11:00",
    "11:30",
    "12:00",
    "13:00",
    "14:00",
)

# Earliest time user may *arm* a same-day schedule (pre-open prep window)
ARMING_OPEN = dt_time(9, 0)
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)
# Angel One / NSE MIS-style forced square-off (algo & paper intraday)
INTRADAY_SQUARE_OFF = dt_time(15, 15)
# Styles that must not carry overnight (matches Angel MIS auto square-off)
SQUARE_OFF_STYLES = frozenset({"INTRADAY", "SCALPING"})

_lock = threading.RLock()
_orders: List[Dict[str, Any]] = []
_worker_started = False
_square_off_worker_started = False


def is_square_off_style(trading_style: Any) -> bool:
    """True for same-day styles that Angel RMS would force-close at 15:15 IST."""
    style = str(trading_style or "").strip().upper().replace(" ", "_")
    return style in SQUARE_OFF_STYLES


def is_past_intraday_square_off(now: datetime) -> bool:
    """True once wall-clock IST is at or after 15:15 (weekends always treat as past for leftovers)."""
    if now.weekday() in (5, 6):
        return True
    return now.time() >= INTRADAY_SQUARE_OFF


def parse_position_open_date(pos: Dict[str, Any]) -> Optional[str]:
    """Best-effort YYYY-MM-DD from paper position timestamp fields."""
    for key in ("timestamp", "closed_at", "timestamp_ist", "armed_at_ist"):
        raw = str(pos.get(key) or "").strip()
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10]
    return None


def position_needs_intraday_square_off(pos: Dict[str, Any], now: datetime) -> bool:
    """
    INTRADAY/SCALPING paper positions must close at 15:15 IST (Angel parity).
    Also closes overnight leftovers that somehow remained OPEN after a prior session.
    """
    if str(pos.get("status") or "OPEN").upper() != "OPEN":
        return False
    if not is_square_off_style(pos.get("trading_style") or pos.get("style")):
        return False
    open_date = parse_position_open_date(pos)
    today = now.strftime("%Y-%m-%d")
    if open_date and open_date < today:
        return True
    return is_past_intraday_square_off(now)


def parse_hhmm(value: str) -> Optional[dt_time]:
    raw = (value or "").strip()
    if not raw or raw.upper() == "IMMEDIATE":
        return None
    try:
        hh, mm = raw.split(":")
        t = dt_time(int(hh), int(mm))
        return t
    except Exception:
        return None


def is_valid_start_slot(value: str) -> bool:
    raw = (value or "").strip()
    if raw.upper() == "IMMEDIATE":
        return True
    return raw in PRESET_START_SLOTS


def can_arm_schedule(now: datetime) -> Tuple[bool, str]:
    """Same-day arming from 09:00 IST on weekdays (prep window before 09:15 open)."""
    if now.weekday() in (5, 6):
        return False, f"Cannot schedule paper trades on {now.strftime('%A')} (weekend)."
    if now.time() < ARMING_OPEN:
        return False, "Scheduling opens at 09:00 AM IST (pre-market prep window)."
    if now.time() > MARKET_CLOSE:
        return False, "Market session ended (after 03:30 PM IST) — cannot arm new schedules today."
    return True, "OK"


def snapshot_plan(plan: Any) -> Dict[str, Any]:
    """Detach plan fields so later ticket edits do not mutate an armed order."""
    trailing = getattr(plan, "trailing_stop", None)
    return {
        "trade_plan_id": getattr(plan, "trade_plan_id", ""),
        "symbol": str(getattr(plan, "symbol", "")).upper(),
        "exchange": getattr(plan, "exchange", "NSE"),
        "trading_style": getattr(plan, "trading_style", "INTRADAY"),
        "strategy": getattr(plan, "strategy", ""),
        "direction": getattr(plan, "direction", "BUY"),
        "entry_price": float(getattr(plan, "entry_price", 0) or 0),
        "quantity": int(getattr(plan, "quantity", 0) or 0),
        "stop_loss_price": float(getattr(plan, "stop_loss_price", 0) or 0),
        "target_price": float(getattr(plan, "target_price", 0) or 0),
        "trailing_stop_amount": float(getattr(trailing, "trail_amount", 20.0) or 20.0) if trailing else 20.0,
        "trailing_enabled": bool(getattr(trailing, "enabled", True)) if trailing else True,
        "trailing_trigger": float(getattr(trailing, "current_trigger_price", 0) or 0) if trailing else 0.0,
        "capital_required": float(getattr(plan, "capital_required", 0) or 0),
        "max_loss_amount": float(getattr(plan, "max_loss_amount", 0) or 0),
        "potential_profit_amount": float(getattr(plan, "potential_profit_amount", 0) or 0),
        "execution_mode": getattr(plan, "execution_mode", "PAPER_TRADING"),
    }


def plan_from_snapshot(snap: Dict[str, Any]):
    from trading_app.trade_ticket_engine import TradePlan, TrailingStopConfig, AutoExitConfig

    trail = TrailingStopConfig(
        enabled=bool(snap.get("trailing_enabled", True)),
        trail_amount=float(snap.get("trailing_stop_amount") or 20.0),
        current_trigger_price=float(snap.get("trailing_trigger") or 0.0),
    )
    return TradePlan(
        trade_plan_id=str(snap.get("trade_plan_id") or f"sched_{uuid.uuid4().hex[:8]}"),
        symbol=str(snap.get("symbol") or "").upper(),
        exchange=str(snap.get("exchange") or "NSE"),
        trading_style=str(snap.get("trading_style") or "INTRADAY"),
        strategy=str(snap.get("strategy") or ""),
        direction=str(snap.get("direction") or "BUY"),
        entry_price=float(snap.get("entry_price") or 0),
        quantity=int(snap.get("quantity") or 0),
        capital_required=float(snap.get("capital_required") or 0),
        stop_loss_price=float(snap.get("stop_loss_price") or 0),
        target_price=float(snap.get("target_price") or 0),
        trailing_stop=trail,
        auto_exit=AutoExitConfig(),
        max_loss_amount=float(snap.get("max_loss_amount") or 0),
        potential_profit_amount=float(snap.get("potential_profit_amount") or 0),
        execution_mode=str(snap.get("execution_mode") or "PAPER_TRADING"),
    )


def arm_order(
    plan: Any,
    start_hhmm: str,
    *,
    now: datetime,
    allow_weekend: bool = False,
) -> Dict[str, Any]:
    """
    Arm a same-day scheduled paper order.

    Returns dict with success/error and order payload when armed.
    """
    slot = (start_hhmm or "").strip()
    if not is_valid_start_slot(slot):
        return {
            "success": False,
            "error": f"Invalid start time '{start_hhmm}'. Choose one of: IMMEDIATE, {', '.join(PRESET_START_SLOTS)}",
        }

    if slot.upper() == "IMMEDIATE":
        return {"success": False, "error": "Use Execute Paper Trade for IMMEDIATE starts.", "immediate": True}

    if now.weekday() in (5, 6) and not allow_weekend:
        return {"success": False, "error": f"Cannot schedule on {now.strftime('%A')} (weekend)."}

    ok_arm, arm_reason = can_arm_schedule(now)
    if not ok_arm and not allow_weekend:
        return {"success": False, "error": arm_reason}

    start_t = parse_hhmm(slot)
    if start_t is None:
        return {"success": False, "error": "Could not parse start time."}
    if start_t < MARKET_OPEN or start_t > MARKET_CLOSE:
        return {"success": False, "error": "Scheduled start must be within 09:15–15:30 IST."}

    # If start already passed today and market still open → caller should execute now
    if now.time() >= start_t:
        return {
            "success": False,
            "error": f"Start time {slot} IST already passed — use Execute Paper Trade now.",
            "already_due": True,
            "start_hhmm": slot,
        }

    order_id = f"sched_{uuid.uuid4().hex[:10]}"
    order = {
        "schedule_id": order_id,
        "status": "ARMED",
        "start_hhmm": slot,
        "scheduled_date": now.strftime("%Y-%m-%d"),
        "armed_at_ist": now.strftime("%Y-%m-%d %H:%M:%S"),
        "plan": snapshot_plan(plan),
        "symbol": str(getattr(plan, "symbol", "")).upper(),
        "direction": getattr(plan, "direction", "BUY"),
        "strategy": getattr(plan, "strategy", ""),
        "quantity": int(getattr(plan, "quantity", 0) or 0),
        "last_error": None,
        "executed_at_ist": None,
    }
    with _lock:
        _orders.append(order)
    logger.info("Armed scheduled paper order %s for %s at %s IST", order_id, order["symbol"], slot)
    return {
        "success": True,
        "message": (
            f"Paper trade ARMED for {order['symbol']} at {slot} IST. "
            f"Fill will use live Angel WebSocket LTP at start time (not the ticket entry price)."
        ),
        "order": deepcopy(order),
    }


def list_orders(*, include_done: bool = True) -> List[Dict[str, Any]]:
    with _lock:
        # Heal stale UI state: FILLED must not keep a prior retry last_error.
        for o in _orders:
            if o.get("status") == "FILLED" and o.get("last_error"):
                o["last_error"] = None
        rows = [deepcopy(o) for o in _orders]
    if not include_done:
        rows = [o for o in rows if o.get("status") == "ARMED"]
    return rows


def cancel_order(schedule_id: str) -> Dict[str, Any]:
    with _lock:
        for o in _orders:
            if o.get("schedule_id") == schedule_id and o.get("status") == "ARMED":
                o["status"] = "CANCELLED"
                return {"success": True, "message": f"Cancelled {schedule_id}", "order": deepcopy(o)}
    return {"success": False, "error": f"No ARMED order found for {schedule_id}"}


def due_armed_orders(now: datetime) -> List[Dict[str, Any]]:
    """Return ARMED orders whose start time has been reached on the scheduled date."""
    due: List[Dict[str, Any]] = []
    today = now.strftime("%Y-%m-%d")
    with _lock:
        for o in _orders:
            if o.get("status") != "ARMED":
                continue
            if o.get("scheduled_date") != today:
                # Expire prior-day leftovers
                if o.get("scheduled_date", "") < today:
                    o["status"] = "EXPIRED"
                    o["last_error"] = "Schedule date passed without fill"
                continue
            start_t = parse_hhmm(str(o.get("start_hhmm") or ""))
            if start_t and now.time() >= start_t:
                due.append(deepcopy(o))
    return due


def mark_order(schedule_id: str, status: str, *, error: Optional[str] = None, executed_at: Optional[str] = None) -> None:
    with _lock:
        for o in _orders:
            if o.get("schedule_id") == schedule_id:
                o["status"] = status
                # Clear stale retry errors on success; otherwise keep/update last_error.
                if status == "FILLED":
                    o["last_error"] = None
                elif error is not None:
                    o["last_error"] = error
                if executed_at is not None:
                    o["executed_at_ist"] = executed_at
                break


def start_scheduler_worker(
    *,
    now_fn: Callable[[], datetime],
    market_open_fn: Callable[[], Tuple[bool, str]],
    fill_fn: Callable[[Any], Dict[str, Any]],
    interval_sec: float = 5.0,
) -> None:
    """Idempotent background worker — fires due ARMED orders when market is open."""
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True

    def _loop():
        while True:
            try:
                now = now_fn()
                open_ok, open_reason = market_open_fn()
                if open_ok:
                    for order in due_armed_orders(now):
                        sid = order.get("schedule_id")
                        try:
                            plan = plan_from_snapshot(order.get("plan") or {})
                            result = fill_fn(plan)
                            if result.get("success"):
                                mark_order(
                                    sid,
                                    "FILLED",
                                    executed_at=now.strftime("%Y-%m-%d %H:%M:%S"),
                                )
                                logger.info("Scheduled paper order %s FILLED", sid)
                            else:
                                # Keep ARMED and retry until market close if transient LTP/mandate issues
                                err = str(result.get("error") or "fill failed")
                                mark_order(sid, "ARMED", error=err)
                                logger.warning("Scheduled fill retry %s: %s", sid, err)
                        except Exception as exc:
                            mark_order(sid, "ARMED", error=str(exc))
                            logger.exception("Scheduled fill error for %s", sid)
                else:
                    # After close, expire remaining same-day armed orders
                    if now.time() > MARKET_CLOSE:
                        with _lock:
                            for o in _orders:
                                if o.get("status") == "ARMED" and o.get("scheduled_date") == now.strftime("%Y-%m-%d"):
                                    o["status"] = "EXPIRED"
                                    o["last_error"] = open_reason
            except Exception:
                logger.exception("Scheduler worker loop error")
            threading.Event().wait(interval_sec)

    t = threading.Thread(target=_loop, name="PaperTradeScheduler", daemon=True)
    t.start()
    logger.info("Paper trade scheduler worker started (interval=%.1fs)", interval_sec)


def start_square_off_worker(
    *,
    now_fn: Callable[[], datetime],
    square_off_fn: Callable[[], Dict[str, Any]],
    interval_sec: float = 15.0,
) -> None:
    """
    Idempotent worker — at/after 15:15 IST forces INTRADAY/SCALPING paper square-off
    (Angel One MIS parity). Also sweeps overnight leftovers.
    """
    global _square_off_worker_started
    with _lock:
        if _square_off_worker_started:
            return
        _square_off_worker_started = True

    def _loop():
        while True:
            try:
                # square_off_fn filters via position_needs_intraday_square_off
                # (15:15 same-day + overnight leftovers).
                out = square_off_fn()
                closed = int((out or {}).get("closed_count") or 0)
                if closed:
                    logger.warning(
                        "AUTO SQUARE-OFF 15:15 IST closed %d paper position(s) at %s",
                        closed,
                        now_fn().strftime("%H:%M:%S"),
                    )
            except Exception:
                logger.exception("Paper square-off worker loop error")
            threading.Event().wait(interval_sec)

    t = threading.Thread(target=_loop, name="PaperIntradaySquareOff", daemon=True)
    t.start()
    logger.info(
        "Paper intraday square-off worker started (cutoff=%s IST, interval=%.1fs)",
        INTRADAY_SQUARE_OFF.strftime("%H:%M"),
        interval_sec,
    )
