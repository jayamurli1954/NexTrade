"""Performance metrics for ARASS research reports."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass
class ArassMetrics:
    total_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    consecutive_wins_max: int = 0
    consecutive_losses_max: int = 0
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    exposure_pct: float = 0.0
    total_brokerage: float = 0.0
    total_slippage: float = 0.0
    total_charges: float = 0.0
    avg_margin_util_pct: float = 0.0
    filter_pass_days: int = 0
    candidate_days: int = 0
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    yearly_returns: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _max_streak(flags: Sequence[bool]) -> int:
    best = cur = 0
    for f in flags:
        if f:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def compute_metrics(
    trades: List[Dict[str, Any]],
    *,
    equity_curve: Sequence[float],
    initial_capital: float,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    traded_bars: int = 0,
    total_bars: int = 0,
    filter_pass_days: int = 0,
    candidate_days: int = 0,
) -> ArassMetrics:
    pnls = [float(t.get("pnl_net", 0.0)) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    win_flags = [p > 0 for p in pnls]
    loss_flags = [p <= 0 for p in pnls]

    eq = np.asarray(equity_curve, dtype=float) if len(equity_curve) else np.asarray([initial_capital])
    rets = np.diff(eq) / np.where(eq[:-1] == 0, np.nan, eq[:-1])
    rets = rets[np.isfinite(rets)]
    downside = rets[rets < 0]

    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak == 0, np.nan, peak)
    max_dd = float(abs(np.nanmin(dd))) * 100.0 if len(dd) else 0.0

    total_return = (float(eq[-1]) / initial_capital - 1.0) * 100.0 if initial_capital else 0.0

    years = 1.0
    if period_start and period_end:
        try:
            years = max((pd.Timestamp(period_end) - pd.Timestamp(period_start)).days / 365.25, 1 / 365.25)
        except Exception:
            years = 1.0
    cagr = ((float(eq[-1]) / initial_capital) ** (1.0 / years) - 1.0) * 100.0 if initial_capital > 0 else 0.0

    vol = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    # Assume equity points ≈ trading days
    sharpe = float(np.mean(rets) / vol * math.sqrt(252)) if vol > 0 else 0.0
    dvol = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = float(np.mean(rets) / dvol * math.sqrt(252)) if dvol > 0 else 0.0
    calmar = float(cagr / max_dd) if max_dd > 0 else 0.0
    recovery = float((eq[-1] - initial_capital) / (max_dd / 100.0 * initial_capital)) if max_dd > 0 else 0.0

    # Monthly / yearly from trade closes
    monthly: Dict[str, float] = {}
    yearly: Dict[str, float] = {}
    for t in trades:
        exit_ts = str(t.get("exit_time", ""))[:10]
        if not exit_ts:
            continue
        mkey = exit_ts[:7]
        ykey = exit_ts[:4]
        monthly[mkey] = monthly.get(mkey, 0.0) + float(t.get("pnl_net", 0.0))
        yearly[ykey] = yearly.get(ykey, 0.0) + float(t.get("pnl_net", 0.0))
    if initial_capital:
        monthly = {k: v / initial_capital * 100.0 for k, v in monthly.items()}
        yearly = {k: v / initial_capital * 100.0 for k, v in yearly.items()}

    return ArassMetrics(
        total_trades=len(trades),
        win_rate_pct=(len(wins) / len(pnls) * 100.0) if pnls else 0.0,
        profit_factor=(gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0),
        expectancy=(sum(pnls) / len(pnls)) if pnls else 0.0,
        avg_win=(sum(wins) / len(wins)) if wins else 0.0,
        avg_loss=(sum(losses) / len(losses)) if losses else 0.0,
        consecutive_wins_max=_max_streak(win_flags),
        consecutive_losses_max=_max_streak(loss_flags),
        total_return_pct=total_return,
        cagr_pct=cagr,
        annualized_return_pct=cagr,
        max_drawdown_pct=max_dd,
        recovery_factor=recovery,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        exposure_pct=(traded_bars / total_bars * 100.0) if total_bars else 0.0,
        total_brokerage=sum(float(t.get("brokerage", 0.0)) for t in trades),
        total_slippage=sum(float(t.get("slippage", 0.0)) for t in trades),
        total_charges=sum(float(t.get("charges_total", 0.0)) for t in trades),
        avg_margin_util_pct=float(np.mean([float(t.get("margin_util_pct", 0.0)) for t in trades])) if trades else 0.0,
        filter_pass_days=filter_pass_days,
        candidate_days=candidate_days,
        monthly_returns=dict(sorted(monthly.items())),
        yearly_returns=dict(sorted(yearly.items())),
    )
