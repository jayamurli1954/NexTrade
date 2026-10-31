"""
NexTrade Phase 7 — Unified Paper Trading Simulator.

Executes paper trading across 4 modes (Manual, Assisted, Strategy, Automated Simulation)
sharing the exact same Protection Lifecycle state machine as live execution (U3 parity).
"""

import time
import uuid
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from .trade_ticket_engine import TradePlan, TradeTicketEngine
from observability.tamper_evident_logger import TamperEvidentLogger

logger = logging.getLogger("PaperTradingSimulator")


class PaperTradingMode(Enum):
    MANUAL = "MANUAL"
    ASSISTED = "ASSISTED"
    STRATEGY = "STRATEGY"
    AUTOMATED_SIMULATION = "AUTOMATED_SIMULATION"


class PositionStatus(Enum):
    OPEN = "OPEN"
    CLOSED_TARGET_HIT = "CLOSED_TARGET_HIT"
    CLOSED_STOP_LOSS_HIT = "CLOSED_STOP_LOSS_HIT"
    CLOSED_TRAILING_STOP_HIT = "CLOSED_TRAILING_STOP_HIT"
    CLOSED_MARKET_CLOSE = "CLOSED_MARKET_CLOSE"
    CLOSED_MANUAL = "CLOSED_MANUAL"


@dataclass
class ActivePaperPosition:
    position_id: str
    trade_plan: TradePlan
    current_price: float
    high_water_mark: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trailing_stop_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    opened_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    exit_price: Optional[float] = None


class PaperTradingSimulator:
    """
    Paper Trading Engine enforcing U3 Behavioural Parity with live execution.
    """

    def __init__(self, logger_audit: Optional[TamperEvidentLogger] = None) -> None:
        self.audit_logger = logger_audit or TamperEvidentLogger(log_filepath="logs/tamper_evident_paper.log")
        self.ticket_engine = TradeTicketEngine()
        self.active_positions: Dict[str, ActivePaperPosition] = {}
        self.closed_positions: List[ActivePaperPosition] = []

    def start_paper_trade(self, plan: TradePlan, mode: PaperTradingMode = PaperTradingMode.MANUAL) -> ActivePaperPosition:
        """
        Activates a paper trade position bound to the Trade Plan.
        """
        pos_id = f"paper_pos_{uuid.uuid4().hex[:8]}"
        initial_tsl = plan.entry_price - plan.trailing_stop.trail_amount if plan.direction == "BUY" else plan.entry_price + plan.trailing_stop.trail_amount

        pos = ActivePaperPosition(
            position_id=pos_id,
            trade_plan=plan,
            current_price=plan.entry_price,
            high_water_mark=plan.entry_price,
            trailing_stop_price=initial_tsl,
            status=PositionStatus.OPEN
        )
        self.active_positions[pos_id] = pos

        self.audit_logger.append_audit_event("PAPER_TRADE_STARTED", {
            "position_id": pos_id,
            "mode": mode.name,
            "symbol": plan.symbol,
            "entry_price": plan.entry_price,
            "quantity": plan.quantity,
            "stop_loss": plan.stop_loss_price,
            "target": plan.target_price,
            "currency": plan.currency
        })

        logger.info("Paper Trade Started: %s on %s | Mode: %s", pos_id, plan.symbol, mode.name)
        return pos

    def process_market_tick(self, position_id: str, new_price: float) -> Tuple[PositionStatus, float, str]:
        """
        Evaluates a market price tick against position SL, TP, Trailing Stop, and Auto-Exit rules.
        """
        pos = self.active_positions.get(position_id)
        if not pos or pos.status != PositionStatus.OPEN:
            return PositionStatus.CLOSED_MANUAL, 0.0, "Position not active"

        plan = pos.trade_plan
        pos.current_price = new_price

        # Update P&L and Trailing SL for BUY order
        if plan.direction == "BUY":
            pos.unrealized_pnl = (new_price - plan.entry_price) * plan.quantity
            if new_price > pos.high_water_mark:
                pos.high_water_mark = new_price
                if plan.trailing_stop.enabled:
                    pos.trailing_stop_price = max(pos.trailing_stop_price, new_price - plan.trailing_stop.trail_amount)

            # Auto-Exit Check 1: Target Hit
            if plan.auto_exit.exit_on_target and new_price >= plan.target_price:
                return self._close_position(pos, new_price, PositionStatus.CLOSED_TARGET_HIT, "Target price reached")

            # Auto-Exit Check 2: Trailing Stop Hit
            if plan.auto_exit.exit_on_trailing_stop and plan.trailing_stop.enabled and new_price <= pos.trailing_stop_price:
                return self._close_position(pos, new_price, PositionStatus.CLOSED_TRAILING_STOP_HIT, "Trailing stop loss hit")

            # Auto-Exit Check 3: Original Stop Loss Hit
            if plan.auto_exit.exit_on_stop_loss and new_price <= plan.stop_loss_price:
                return self._close_position(pos, new_price, PositionStatus.CLOSED_STOP_LOSS_HIT, "Stop loss price hit")

        else: # SELL order
            pos.unrealized_pnl = (plan.entry_price - new_price) * plan.quantity
            if new_price < pos.high_water_mark:
                pos.high_water_mark = new_price
                if plan.trailing_stop.enabled:
                    pos.trailing_stop_price = min(pos.trailing_stop_price, new_price + plan.trailing_stop.trail_amount)

            if plan.auto_exit.exit_on_target and new_price <= plan.target_price:
                return self._close_position(pos, new_price, PositionStatus.CLOSED_TARGET_HIT, "Target price reached")

            if plan.auto_exit.exit_on_trailing_stop and plan.trailing_stop.enabled and new_price >= pos.trailing_stop_price:
                return self._close_position(pos, new_price, PositionStatus.CLOSED_TRAILING_STOP_HIT, "Trailing stop loss hit")

            if plan.auto_exit.exit_on_stop_loss and new_price >= plan.stop_loss_price:
                return self._close_position(pos, new_price, PositionStatus.CLOSED_STOP_LOSS_HIT, "Stop loss price hit")

        return PositionStatus.OPEN, pos.unrealized_pnl, "Position active"

    def force_market_close_exits(
        self,
        now=None,
        exit_prices: Optional[Dict[str, float]] = None,
    ) -> List[Tuple[str, PositionStatus, float, str]]:
        """
        Angel One MIS parity: close open positions with exit_on_market_close at/after 15:15 IST.
        INTRADAY/SCALPING styles only. `now` should be timezone-aware IST datetime when provided.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from trading_app.paper_trade_scheduler import (
            INTRADAY_SQUARE_OFF,
            is_square_off_style,
            is_past_intraday_square_off,
        )

        if now is None:
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
        if not is_past_intraday_square_off(now):
            return []

        results: List[Tuple[str, PositionStatus, float, str]] = []
        prices = exit_prices or {}
        for pos_id, pos in list(self.active_positions.items()):
            plan = pos.trade_plan
            if not getattr(plan.auto_exit, "exit_on_market_close", True):
                continue
            if not is_square_off_style(getattr(plan, "trading_style", "INTRADAY")):
                continue
            exit_px = float(prices.get(plan.symbol) or pos.current_price or plan.entry_price)
            status, pnl, reason = self._close_position(
                pos,
                exit_px,
                PositionStatus.CLOSED_MARKET_CLOSE,
                f"Market close square-off at {INTRADAY_SQUARE_OFF.strftime('%H:%M')} IST",
            )
            results.append((pos_id, status, pnl, reason))
        return results

    def _close_position(self, pos: ActivePaperPosition, exit_price: float, status: PositionStatus, reason: str) -> Tuple[PositionStatus, float, str]:
        """Closes an active paper trade position and logs the audit record."""
        pos.status = status
        pos.exit_price = exit_price
        pos.closed_at = time.time()
        
        if pos.trade_plan.direction == "BUY":
            pos.realized_pnl = (exit_price - pos.trade_plan.entry_price) * pos.trade_plan.quantity
        else:
            pos.realized_pnl = (pos.trade_plan.entry_price - exit_price) * pos.trade_plan.quantity

        pos.unrealized_pnl = 0.0

        if pos.position_id in self.active_positions:
            del self.active_positions[pos.position_id]
        self.closed_positions.append(pos)

        self.audit_logger.append_audit_event("PAPER_TRADE_AUTO_EXITED", {
            "position_id": pos.position_id,
            "status": status.name,
            "reason": reason,
            "exit_price": exit_price,
            "realized_pnl": pos.realized_pnl,
            "currency": pos.trade_plan.currency
        })

        logger.info("Paper Trade Auto-Exited: %s | Status: %s | P&L: ₹%.2f", pos.position_id, status.name, pos.realized_pnl)
        return status, pos.realized_pnl, reason

    def manual_exit_position(self, position_id: str) -> Tuple[PositionStatus, float, str]:
        """Manually exits an active paper trade position."""
        pos = self.active_positions.get(position_id)
        if not pos:
            return PositionStatus.CLOSED_MANUAL, 0.0, "Position not found"
        return self._close_position(pos, pos.current_price, PositionStatus.CLOSED_MANUAL, "User manual market exit")
