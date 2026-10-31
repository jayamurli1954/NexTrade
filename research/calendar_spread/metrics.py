"""Metrics for calendar-spread research reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class CalendarMetrics:
    total_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_monthly_return_pct: float = 0.0
    months_in_target_2_to_4: int = 0
    months_total: int = 0
    pts_band_hits: int = 0
    pts_band_candidates: int = 0
    pts_band_hit_rate_pct: float = 0.0
    total_charges: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    exit_reasons: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_calendar_metrics(
    trades: List[Dict[str, Any]],
    *,
    equity_curve: Sequence[float],
    initial_capital: float,
    pts_band_hits: int = 0,
    pts_band_candidates: int = 0,
) -> CalendarMetrics:
    pnls = [float(t.get("pnl_net", 0.0)) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    eq = np.asarray(equity_curve, dtype=float) if len(equity_curve) else np.asarray([initial_capital])
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak == 0, np.nan, peak)
    max_dd = float(np.nanmin(dd) * 100.0) if len(dd) else 0.0

    monthly: Dict[str, float] = {}
    for t in trades:
        m = str(t.get("exit_date") or t.get("entry_date") or "")[:7]
        if not m:
            continue
        monthly[m] = monthly.get(m, 0.0) + float(t.get("pnl_net", 0.0))
    # capital-normalized monthly %
    monthly_pct = {k: (v / float(initial_capital) * 100.0) for k, v in sorted(monthly.items())}
    in_band = sum(1 for v in monthly_pct.values() if 2.0 <= v <= 4.0)

    reasons: Dict[str, int] = {}
    for t in trades:
        r = str(t.get("exit_reason") or "UNKNOWN")
        reasons[r] = reasons.get(r, 0) + 1

    n = len(pnls)
    hit_rate = (pts_band_hits / pts_band_candidates * 100.0) if pts_band_candidates else 0.0
    return CalendarMetrics(
        total_trades=n,
        win_rate_pct=round((len(wins) / n * 100.0) if n else 0.0, 2),
        profit_factor=round(pf if np.isfinite(pf) else 0.0, 4),
        expectancy=round((sum(pnls) / n) if n else 0.0, 2),
        total_return_pct=round((float(eq[-1]) - float(initial_capital)) / float(initial_capital) * 100.0, 2),
        max_drawdown_pct=round(max_dd, 2),
        avg_monthly_return_pct=round(float(np.mean(list(monthly_pct.values()))) if monthly_pct else 0.0, 2),
        months_in_target_2_to_4=in_band,
        months_total=len(monthly_pct),
        pts_band_hits=int(pts_band_hits),
        pts_band_candidates=int(pts_band_candidates),
        pts_band_hit_rate_pct=round(hit_rate, 2),
        total_charges=round(sum(float(t.get("charges", 0.0)) for t in trades), 2),
        gross_pnl=round(sum(float(t.get("pnl_gross", 0.0)) for t in trades), 2),
        net_pnl=round(sum(pnls), 2),
        monthly_returns={k: round(v, 2) for k, v in monthly_pct.items()},
        exit_reasons=reasons,
    )
