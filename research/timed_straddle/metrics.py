"""Summary statistics for timed-straddle backtest results."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


def summarize(trades: pd.DataFrame, margin_per_trade: float) -> Dict[str, Any]:
    if trades.empty:
        return {"trades": 0}
    pnl = trades["pnl"].to_numpy()
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    dd = eq - peak
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    years = max((trades["date"].max() - trades["date"].min()).days / 365.25, 1e-9)
    sharpe = float(pnl.mean() / pnl.std(ddof=1) * np.sqrt(252)) if len(pnl) > 1 and pnl.std() > 0 else 0.0
    worst = trades.loc[trades["pnl"].idxmin()]
    return {
        "trades": int(len(pnl)),
        "period": f"{trades['date'].min().date()} .. {trades['date'].max().date()}",
        "net_pnl": round(float(pnl.sum()), 0),
        "avg_pnl": round(float(pnl.mean()), 0),
        "win_rate_pct": round(len(wins) / len(pnl) * 100.0, 1),
        "avg_win": round(float(wins.mean()), 0) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 0) if len(losses) else 0.0,
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
        "max_drawdown": round(float(dd.min()), 0),
        "sharpe_daily_ann": round(sharpe, 2),
        "total_costs": round(float(trades["costs"].sum()), 0),
        "margin_assumed": margin_per_trade,
        "cagr_on_margin_pct": round(float(pnl.sum()) / margin_per_trade / years * 100.0, 1),
        "max_dd_pct_of_margin": round(float(dd.min()) / margin_per_trade * 100.0, 1),
        "worst_day": {"date": str(worst["date"].date()), "pnl": round(float(worst["pnl"]), 0)},
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
    }


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    g = trades.groupby(by)["pnl"]
    out = pd.DataFrame({
        "trades": g.size(),
        "net_pnl": g.sum().round(0),
        "avg_pnl": g.mean().round(0),
        "win_rate_pct": (g.apply(lambda s: (s > 0).mean() * 100.0)).round(1),
        "worst": g.min().round(0),
    })
    return out
