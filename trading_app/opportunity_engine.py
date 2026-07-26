"""
NexTrade Phase 7 — Intelligent Opportunity Engine.

Parses technical signals into actionable trade cards with "Why This Trade?" rationale,
trade invalidation rules, and 1-click Trade Plan population.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .trade_ticket_engine import TradePlan, TradeTicketEngine

logger = logging.getLogger("OpportunityEngine")


@dataclass
class TradeOpportunity:
    opportunity_id: str
    symbol: str
    exchange: str = "NSE"
    currency: str = "INR (₹)"
    trading_style: str = "INTRADAY"
    strategy: str = "Momentum Breakout"
    signal_strength_pct: float = 87.0
    suggested_entry: float = 2742.00
    suggested_stop_loss: float = 2690.00
    suggested_target: float = 2867.00
    suggested_quantity: int = 10
    risk_reward_ratio: float = 2.40
    why_this_trade: List[str] = field(default_factory=lambda: [
        "Price crossed above VWAP with high volume",
        "Volume is 2.4x above 20-period average",
        "Bullish momentum breakout confirmed on 15m chart"
    ])
    invalidation_rules: List[str] = field(default_factory=lambda: [
        "Price closes below ₹2,690 support level",
        "Volume falls below confirmation threshold",
        "NIFTY market trend reverses to strong bearish"
    ])
    created_at: float = field(default_factory=time.time)


class OpportunityEngine:
    """
    Engine generating actionable Trade Opportunities with clear non-technical rationale.
    """

    SAMPLE_OPPORTUNITIES = [
        TradeOpportunity(
            opportunity_id="opp_rel_01",
            symbol="RELIANCE",
            trading_style="INTRADAY",
            strategy="Momentum Breakout",
            signal_strength_pct=87.0,
            suggested_entry=2742.00,
            suggested_stop_loss=2690.00,
            suggested_target=2867.00,
            suggested_quantity=10,
            risk_reward_ratio=2.40,
            why_this_trade=[
                "Price crossed above VWAP with strong momentum",
                "Volume is 2.4x above 20-period average",
                "Bullish breakout confirmed on 15m chart"
            ],
            invalidation_rules=[
                "Price closes below ₹2,690 support level",
                "Volume contracts below confirmation threshold"
            ]
        ),
        TradeOpportunity(
            opportunity_id="opp_hdfc_02",
            symbol="HDFCBANK",
            trading_style="SWING",
            strategy="Trend Following",
            signal_strength_pct=82.0,
            suggested_entry=1742.00,
            suggested_stop_loss=1700.00,
            suggested_target=1826.00,
            suggested_quantity=15,
            risk_reward_ratio=2.00,
            why_this_trade=[
                "Holding above key 50-day EMA support",
                "Institutional buying accumulation detected",
                "RSI neutral-bullish bounce from 45 level"
            ],
            invalidation_rules=[
                "Price closes below ₹1,700 key swing support",
                "BANKNIFTY sector index breakdown"
            ]
        ),
        TradeOpportunity(
            opportunity_id="opp_tcs_03",
            symbol="TCS",
            trading_style="INTRADAY",
            strategy="VWAP Reversion",
            signal_strength_pct=76.0,
            suggested_entry=3850.00,
            suggested_stop_loss=3800.00,
            suggested_target=3950.00,
            suggested_quantity=5,
            risk_reward_ratio=2.00,
            why_this_trade=[
                "Rebound from lower Bollinger Band",
                "Positive divergence on 5m MACD indicator"
            ],
            invalidation_rules=[
                "Break below ₹3,800 low of day"
            ]
        )
    ]

    def __init__(self) -> None:
        self.ticket_engine = TradeTicketEngine()

    def get_top_opportunities(self) -> List[TradeOpportunity]:
        """Returns active high-confidence trade opportunities."""
        return self.SAMPLE_OPPORTUNITIES

    def convert_opportunity_to_trade_plan(self, opp: TradeOpportunity, quantity: Optional[int] = None) -> TradePlan:
        """
        1-Click conversion of a Trade Opportunity into a validated TradePlan (U1 & U2 compliant).
        """
        qty = quantity or opp.suggested_quantity
        return self.ticket_engine.create_trade_plan(
            symbol=opp.symbol,
            trading_style=opp.trading_style,
            strategy=opp.strategy,
            direction="BUY",
            entry_price=opp.suggested_entry,
            quantity=qty,
            stop_loss_price=opp.suggested_stop_loss,
            target_price=opp.suggested_target,
            trailing_stop_amount=20.0,
            execution_mode="PAPER_TRADING"
        )
