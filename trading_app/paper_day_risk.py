"""
Paper day-level profit / loss flatten rules (experiment).

Combined day PnL = realized (closed today) + unrealized MTM on open positions.
When combined >= profit target → flatten all open paper trades.
When combined <= -loss limit → flatten all open paper trades.

Per-trade SL/TP helpers live here so the web paper path can share one evaluator.
Does not affect live broker execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Defaults (override via storage/paper_day_risk_policy.json or dashboard UI)
PAPER_DAY_PROFIT_TARGET_INR = 1500.0
PAPER_DAY_LOSS_LIMIT_INR = 2000.0

REASON_DAY_PROFIT = "DAY_PROFIT_TARGET"
REASON_DAY_LOSS = "DAY_LOSS_LIMIT"
REASON_TARGET = "AUTO_TARGET_HIT"
REASON_STOP = "AUTO_STOP_LOSS_HIT"


@dataclass(frozen=True)
class DayRiskLimits:
    profit_target_inr: float = PAPER_DAY_PROFIT_TARGET_INR
    loss_limit_inr: float = PAPER_DAY_LOSS_LIMIT_INR


def get_day_risk_limits() -> DayRiskLimits:
    """Load user-defined limits (defaults +₹1500 / −₹2000)."""
    try:
        from trading_app.paper_day_risk_policy import load_policy

        p = load_policy()
        return DayRiskLimits(profit_target_inr=p.profit_target_inr, loss_limit_inr=p.loss_limit_inr)
    except Exception:
        return DayRiskLimits()


def combined_day_pnl(realized_pnl: float, unrealized_pnls: List[float]) -> float:
    return float(realized_pnl or 0.0) + float(sum(float(x or 0.0) for x in unrealized_pnls))


def day_flatten_reason(
    combined_pnl: float,
    limits: Optional[DayRiskLimits] = None,
) -> Optional[str]:
    """Return flatten reason code if day limits breached, else None."""
    lim = limits or get_day_risk_limits()
    if combined_pnl >= float(lim.profit_target_inr):
        return REASON_DAY_PROFIT
    if combined_pnl <= -float(lim.loss_limit_inr):
        return REASON_DAY_LOSS
    return None


def per_trade_exit_reason(
    *,
    direction: str,
    ltp: float,
    target: Optional[float],
    stop_loss: Optional[float],
) -> Optional[str]:
    """Evaluate single-position target / stop vs LTP."""
    try:
        px = float(ltp)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None
    side = str(direction or "BUY").upper()
    try:
        tp = float(target) if target is not None else None
    except (TypeError, ValueError):
        tp = None
    try:
        sl = float(stop_loss) if stop_loss is not None else None
    except (TypeError, ValueError):
        sl = None

    if side in ("SELL", "SHORT"):
        if tp is not None and tp > 0 and px <= tp:
            return REASON_TARGET
        if sl is not None and sl > 0 and px >= sl:
            return REASON_STOP
    else:
        if tp is not None and tp > 0 and px >= tp:
            return REASON_TARGET
        if sl is not None and sl > 0 and px <= sl:
            return REASON_STOP
    return None


def parse_price_field(pos: Dict[str, Any], raw_key: str, fmt_key: str) -> Optional[float]:
    if pos.get(raw_key) is not None:
        try:
            return float(pos.get(raw_key))
        except (TypeError, ValueError):
            pass
    raw = str(pos.get(fmt_key) or "").replace("₹", "").replace(",", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def collect_per_trade_exits(enriched_positions: List[Dict[str, Any]]) -> List[Tuple[str, float, str]]:
    """
    Returns list of (position_id, exit_ltp, reason) for positions that hit SL/TP.
    Requires enriched rows with ltp / pnl when live.
    """
    out: List[Tuple[str, float, str]] = []
    for pos in enriched_positions:
        if str(pos.get("status") or "OPEN").upper() != "OPEN":
            continue
        pid = pos.get("position_id")
        if not pid:
            continue
        try:
            ltp = float(pos.get("ltp") or 0)
        except (TypeError, ValueError):
            ltp = 0.0
        if ltp <= 0:
            continue
        reason = per_trade_exit_reason(
            direction=str(pos.get("direction") or "BUY"),
            ltp=ltp,
            target=parse_price_field(pos, "target_raw", "target"),
            stop_loss=parse_price_field(pos, "stop_loss_raw", "stop_loss"),
        )
        if reason:
            out.append((str(pid), ltp, reason))
    return out
