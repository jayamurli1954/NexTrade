"""ORB research metrics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class OrbMetrics:
    total_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    total_charges: float = 0.0
    trades_per_day_avg: float = 0.0
    symbols_traded: int = 0
    monthly_returns: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_metrics(
    trades: List[Dict[str, Any]],
    *,
    equity_curve: Sequence[float],
    initial_capital: float,
    trading_days: int = 0,
) -> OrbMetrics:
    pnls = [float(t.get("pnl_net", 0.0)) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    eq = np.asarray(equity_curve, dtype=float) if len(equity_curve) else np.asarray([initial_capital])
    rets = np.diff(eq) / np.where(eq[:-1] == 0, np.nan, eq[:-1])
    rets = rets[np.isfinite(rets)]

    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak == 0, np.nan, peak)
    max_dd = float(np.nanmin(dd) * 100.0) if len(dd) else 0.0

    sharpe = 0.0
    if len(rets) > 2 and np.nanstd(rets) > 0:
        sharpe = float(np.nanmean(rets) / np.nanstd(rets) * math.sqrt(252))

    symbols = {str(t.get("symbol")) for t in trades}
    days = {str(t.get("day")) for t in trades if t.get("day")}
    tpd = (len(trades) / len(days)) if days else 0.0

    monthly: Dict[str, float] = {}
    for t in trades:
        day = str(t.get("day") or "")[:7]
        if not day:
            continue
        monthly[day] = monthly.get(day, 0.0) + float(t.get("pnl_net", 0.0))
    for k in list(monthly):
        monthly[k] = round(100.0 * monthly[k] / initial_capital, 4)

    return OrbMetrics(
        total_trades=len(trades),
        win_rate_pct=round(100.0 * len(wins) / len(pnls), 2) if pnls else 0.0,
        profit_factor=round(gross_win / gross_loss, 3) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        expectancy=round(float(np.mean(pnls)), 2) if pnls else 0.0,
        avg_win=round(float(np.mean(wins)), 2) if wins else 0.0,
        avg_loss=round(float(np.mean(losses)), 2) if losses else 0.0,
        total_return_pct=round(100.0 * (float(eq[-1]) - initial_capital) / initial_capital, 3),
        max_drawdown_pct=round(max_dd, 3),
        sharpe=round(sharpe, 3),
        total_charges=round(sum(float(t.get("costs", 0.0)) for t in trades), 2),
        trades_per_day_avg=round(tpd, 3),
        symbols_traded=len(symbols),
        monthly_returns=dict(sorted(monthly.items())),
    )
