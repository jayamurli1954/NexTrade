"""
Paper / journal analytics helpers for Excel export and dashboards.

Computes today-vs-period metrics, drawdown, expectancy, and strategy/day breakdowns
from EXECUTED_TRADES_LOG-style dicts. Research/reporting only — not live risk authority.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from trading_app.broker_charges import AngelOneEquityIntradayCharges, estimate_round_trip_total


def _pnl(t: Dict[str, Any]) -> float:
    try:
        return float(t.get("pnl") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _trade_day(t: Dict[str, Any]) -> str:
    for key in ("timestamp", "closed_at", "exit_time", "timestamp_ist"):
        raw = str(t.get(key) or "").strip()
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10]
    return ""


def _closed_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for t in trades or []:
        if str(t.get("status") or "CLOSED").upper() == "OPEN":
            continue
        out.append(t)
    return out


def estimate_round_trip_charges(
    *,
    entry: float,
    exit_px: float,
    qty: int,
    brokerage_per_order: float = 20.0,
    slip_pct: float = 0.05,
    charge_model: Optional[AngelOneEquityIntradayCharges] = None,
) -> float:
    """Round-trip charge total (Angel One equity intraday template by default)."""
    model = charge_model or AngelOneEquityIntradayCharges(
        brokerage_per_order_inr=brokerage_per_order,
        slippage_pct=slip_pct,
    )
    return estimate_round_trip_total(entry=entry, exit_px=exit_px, qty=qty, model=model)


def enrich_trade_with_net(t: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(t)
    gross = _pnl(t)
    charges = estimate_round_trip_charges(
        entry=float(t.get("entry_price") or 0),
        exit_px=float(t.get("exit_price") or 0),
        qty=int(t.get("quantity") or 0),
    )
    row["gross_pnl"] = round(gross, 2)
    row["est_charges"] = round(charges, 2)
    row["net_pnl"] = round(gross - charges, 2)
    return row


@dataclass
class JournalMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    est_charges: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_consecutive_losses: int = 0
    period_start: str = ""
    period_end: str = ""
    daily: Dict[str, float] = field(default_factory=dict)
    by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_direction: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _max_consecutive_losses(pnls: List[float]) -> int:
    best = cur = 0
    for p in pnls:
        if p <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _max_drawdown(pnls: List[float]) -> float:
    """Peak-to-trough drawdown in currency (negative or zero)."""
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = eq - peak
        if dd < max_dd:
            max_dd = dd
    return float(max_dd)


def compute_journal_metrics(trades: List[Dict[str, Any]], *, use_net: bool = False) -> JournalMetrics:
    closed = _closed_trades(trades)
    enriched = [enrich_trade_with_net(t) for t in closed]
    key = "net_pnl" if use_net else "gross_pnl"
    pnls = [float(t.get(key) or 0.0) for t in enriched]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    days = sorted({_trade_day(t) for t in enriched if _trade_day(t)})
    daily: Dict[str, float] = defaultdict(float)
    by_dir: Dict[str, float] = defaultdict(float)
    by_strat_pnl: Dict[str, List[float]] = defaultdict(list)

    for t, p in zip(enriched, pnls):
        d = _trade_day(t)
        if d:
            daily[d] += p
        direction = str(t.get("direction") or "").upper() or "?"
        by_dir[direction] += p
        strat = str(t.get("strategy") or "Unknown")
        by_strat_pnl[strat].append(p)

    by_strategy: Dict[str, Dict[str, Any]] = {}
    for strat, plist in by_strat_pnl.items():
        sw = [x for x in plist if x > 0]
        sl = [x for x in plist if x <= 0]
        gw = sum(sw)
        gl = abs(sum(sl))
        by_strategy[strat] = {
            "trades": len(plist),
            "wins": len(sw),
            "losses": len(sl),
            "win_rate_pct": round(len(sw) / len(plist) * 100.0, 1) if plist else 0.0,
            "pnl": round(sum(plist), 2),
            "profit_factor": round(gw / gl, 2) if gl > 0 else (round(gw, 2) if gw > 0 else 0.0),
            "expectancy": round(sum(plist) / len(plist), 2) if plist else 0.0,
        }

    return JournalMetrics(
        total_trades=len(pnls),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=round(len(wins) / len(pnls) * 100.0, 1) if pnls else 0.0,
        gross_pnl=round(sum(float(t.get("gross_pnl") or 0) for t in enriched), 2),
        net_pnl=round(sum(float(t.get("net_pnl") or 0) for t in enriched), 2),
        est_charges=round(sum(float(t.get("est_charges") or 0) for t in enriched), 2),
        avg_win=round(sum(wins) / len(wins), 2) if wins else 0.0,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else 0.0,
        largest_win=round(max(pnls), 2) if pnls else 0.0,
        largest_loss=round(min(pnls), 2) if pnls else 0.0,
        expectancy=round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        profit_factor=round(gross_win / gross_loss, 2) if gross_loss > 0 else (round(gross_win, 2) if gross_win > 0 else 0.0),
        max_drawdown=round(_max_drawdown(pnls), 2),
        max_consecutive_losses=_max_consecutive_losses(pnls),
        period_start=days[0] if days else "",
        period_end=days[-1] if days else "",
        daily={k: round(v, 2) for k, v in sorted(daily.items())},
        by_strategy=dict(sorted(by_strategy.items(), key=lambda kv: kv[1]["pnl"], reverse=True)),
        by_direction={k: round(v, 2) for k, v in by_dir.items()},
    )


def filter_trades_for_day(trades: List[Dict[str, Any]], day: str) -> List[Dict[str, Any]]:
    day = (day or "")[:10]
    return [t for t in _closed_trades(trades) if _trade_day(t) == day]


def allow_momentum_breakdown_signal(
    signal: Dict[str, Any],
    market_context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Paper experiment gate after journal review (Jul 28–Aug 4):
    Momentum Breakdown (all SELLs) was the only strategy in the red.
    Raise the bar; do not change BUY path.
    """
    ctx = market_context or {}
    try:
        conf = float(signal.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < 0.70:
        return False, f"Momentum Breakdown gated: confidence {conf:.2f} < 0.70"

    try:
        rsi = signal.get("rsi")
        rsi_f = float(rsi) if rsi is not None else None
    except (TypeError, ValueError):
        rsi_f = None
    if rsi_f is not None and rsi_f < 45.0:
        return False, f"Momentum Breakdown gated: RSI {rsi_f:.1f} < 45 (not extended)"

    vix = ctx.get("india_vix")
    try:
        vix_f = float(vix) if vix is not None else None
    except (TypeError, ValueError):
        vix_f = None
    if vix_f is not None and vix_f < 13.0:
        return False, f"Momentum Breakdown gated: India VIX {vix_f:.2f} < 13"

    nifty_chg = ctx.get("nifty_change_pct")
    try:
        n_chg = float(nifty_chg) if nifty_chg is not None else None
    except (TypeError, ValueError):
        n_chg = None
    if n_chg is not None and n_chg > 0.35:
        return False, f"Momentum Breakdown gated: NIFTY day change {n_chg:.2f}% > +0.35%"

    return True, "OK"
