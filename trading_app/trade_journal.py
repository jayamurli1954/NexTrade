"""
NexTrade Phase 7 — Trade Journal & Learning Analytics Engine.

Records completed trades and calculates performance metrics, win rates by strategy,
and P&L breakdowns by trading style in INR (₹).
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TradeJournalEngine")


@dataclass
class JournalEntry:
    entry_id: str
    symbol: str
    trading_style: str
    strategy: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: int
    realized_pnl: float
    status: str
    closed_at: float = field(default_factory=time.time)


class TradeJournalEngine:
    """
    Trade Journal managing trade logs and strategy performance analytics.
    """

    def __init__(self) -> None:
        self.entries: List[JournalEntry] = [
            JournalEntry("j_01", "RELIANCE", "INTRADAY", "Momentum Breakout", "BUY", 2700.0, 2750.0, 10, 500.0, "CLOSED_TARGET_HIT"),
            JournalEntry("j_02", "HDFCBANK", "SWING", "Trend Following", "BUY", 1720.0, 1780.0, 20, 1200.0, "CLOSED_TARGET_HIT"),
            JournalEntry("j_03", "INFY", "SCALPING", "VWAP Scalp", "BUY", 1450.0, 1440.0, 15, -150.0, "CLOSED_STOP_LOSS_HIT"),
            JournalEntry("j_04", "TCS", "INTRADAY", "VWAP Reversion", "BUY", 3800.0, 3860.0, 5, 300.0, "CLOSED_TARGET_HIT"),
        ]

    def add_entry(self, entry: JournalEntry) -> None:
        self.entries.append(entry)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Calculates win rates, strategy performance, and style breakdowns."""
        if not self.entries:
            return {"total_trades": 0, "net_pnl": 0.0, "win_rate_pct": 0.0}

        total = len(self.entries)
        wins = [e for e in self.entries if e.realized_pnl > 0]
        losses = [e for e in self.entries if e.realized_pnl < 0]

        win_rate = (len(wins) / total) * 100.0 if total > 0 else 0.0
        total_pnl = sum(e.realized_pnl for e in self.entries)
        total_win_amt = sum(e.realized_pnl for e in wins)
        total_loss_amt = abs(sum(e.realized_pnl for e in losses))

        avg_winner = total_win_amt / len(wins) if wins else 0.0
        avg_loser = total_loss_amt / len(losses) if losses else 0.0
        profit_factor = round(total_win_amt / total_loss_amt, 2) if total_loss_amt > 0 else total_win_amt

        # Breakdown by Trading Style
        style_pnl: Dict[str, float] = {}
        for e in self.entries:
            style_pnl[e.trading_style] = style_pnl.get(e.trading_style, 0.0) + e.realized_pnl

        # Breakdown by Strategy
        strategy_stats: Dict[str, Dict[str, Any]] = {}
        for e in self.entries:
            if e.strategy not in strategy_stats:
                strategy_stats[e.strategy] = {"total": 0, "wins": 0, "pnl": 0.0}
            strategy_stats[e.strategy]["total"] += 1
            if e.realized_pnl > 0:
                strategy_stats[e.strategy]["wins"] += 1
            strategy_stats[e.strategy]["pnl"] += e.realized_pnl

        return {
            "currency": "INR (₹)",
            "total_trades": total,
            "net_pnl_formatted": f"₹{total_pnl:,.2f}",
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": profit_factor,
            "average_winner_formatted": f"₹{avg_winner:,.2f}",
            "average_loser_formatted": f"₹{avg_loser:,.2f}",
            "style_breakdown_formatted": {k: f"₹{v:,.2f}" for k, v in style_pnl.items()},
            "strategy_stats": strategy_stats
        }
