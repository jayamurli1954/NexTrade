"""
NexTrade Phase 7 — User Experience & Intelligent Trading Workflow Package.
"""

from .trade_ticket_engine import TradeTicketEngine, TradePlan
from .paper_trading_simulator import PaperTradingSimulator, PaperTradingMode
from .opportunity_engine import OpportunityEngine, TradeOpportunity
from .trade_journal import TradeJournalEngine

__all__ = [
    "TradeTicketEngine",
    "TradePlan",
    "PaperTradingSimulator",
    "PaperTradingMode",
    "OpportunityEngine",
    "TradeOpportunity",
    "TradeJournalEngine"
]
