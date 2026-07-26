"""
NexTrade Phase 7 — Universal Trade Ticket Engine.

Constructs, validates, and manages Trade Plans in INR (₹), enforcing UX Safety Invariants U1, U2, and U4.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from brokers.broker_production_gate import BrokerProductionGate

logger = logging.getLogger("TradeTicketEngine")


class MissingProtectionException(Exception):
    """Raised when a trade plan lacks an explicit protection policy (U2 breach)."""
    pass


class UIBoundaryViolationException(Exception):
    """Raised when a UI action attempts to bypass the certified safety control plane (U1 breach)."""
    pass


class UserIntentViolationException(Exception):
    """Raised when an unconfirmed parameter mutation violates User Intent Integrity (U4 breach)."""
    pass


@dataclass
class TrailingStopConfig:
    enabled: bool = True
    trail_amount: float = 20.00
    current_trigger_price: float = 0.0


@dataclass
class AutoExitConfig:
    exit_on_stop_loss: bool = True
    exit_on_target: bool = True
    exit_on_trailing_stop: bool = True
    exit_on_market_close: bool = True


@dataclass
class TradePlan:
    trade_plan_id: str
    symbol: str
    exchange: str = "NSE"
    currency: str = "INR (₹)"
    instrument_type: str = "EQUITY"
    trading_style: str = "INTRADAY"
    strategy: str = "MOMENTUM_BREAKOUT"
    direction: str = "BUY"
    entry_price: float = 2742.00
    quantity: int = 10
    capital_required: float = 27420.00
    stop_loss_price: float = 2690.00
    target_price: float = 2850.00
    trailing_stop: TrailingStopConfig = field(default_factory=TrailingStopConfig)
    auto_exit: AutoExitConfig = field(default_factory=AutoExitConfig)
    max_loss_amount: float = 520.00
    potential_profit_amount: float = 1080.00
    risk_reward_ratio: float = 2.08
    signal_confidence_pct: float = 87.0
    execution_mode: str = "PAPER_TRADING"
    created_at: float = field(default_factory=time.time)
    version: int = 1


class TradeTicketEngine:
    """
    Engine managing Trade Plan creation, pre-execution summary calculation,
    and U1/U2/U4 safety enforcement.
    """

    STYLE_STRATEGY_MAP = {
        "INTRADAY": ["Momentum Breakout", "VWAP Reversion", "RSI Crossover", "Volume Surge"],
        "SCALPING": ["VWAP Scalp", "Opening Range Breakout (ORB)", "Quick Momentum"],
        "SWING": ["Trend Following", "Moving Average Crossover", "Support/Resistance Breakout"],
        "POSITIONAL": ["Long-Term Trend", "Value Accumulation", "Mean Reversion"],
        "OPTIONS_BUYING": ["Momentum Buying", "Volatility Expansion", "ATM Breakout"],
        "OPTIONS_SELLING": ["Credit Spreads", "Iron Condor", "Theta Decay Neutral"]
    }

    def __init__(self, control_plane: Optional[SafetyControlPlane] = None) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.gate = BrokerProductionGate()
        self.control_plane.report_subsystem_state("trade_ticket_engine", SafetyState.READY, "Trade Ticket Engine initialized")

    def get_eligible_strategies(self, trading_style: str) -> List[str]:
        """Returns strategies permitted for the selected trading style."""
        style_key = trading_style.upper().replace(" ", "_")
        return self.STYLE_STRATEGY_MAP.get(style_key, ["Momentum Breakout", "VWAP Reversion"])

    def create_trade_plan(
        self,
        symbol: str,
        trading_style: str,
        strategy: str,
        direction: str,
        entry_price: float,
        quantity: int,
        stop_loss_price: float,
        target_price: float,
        trailing_stop_amount: float = 20.0,
        execution_mode: str = "PAPER_TRADING"
    ) -> TradePlan:
        """
        Constructs a validated Trade Plan in INR (₹) enforcing U1 and U2 invariants.
        """
        # 1. UI Safety Boundary Check (U1)
        if self.control_plane.get_state() not in (SafetyState.SAFE, SafetyState.READY):
            msg = f"UI SAFETY BOUNDARY BREACH (U1): Cannot create trade plan while SafetyControlPlane is in state {self.control_plane.get_state().name}"
            logger.critical(msg)
            raise UIBoundaryViolationException(msg)

        # 2. Mandatory Protection Binding Check (U2)
        if stop_loss_price <= 0 or target_price <= 0:
            msg = "MANDATORY PROTECTION BREACH (U2): Every trade plan must have an explicit Stop Loss and Target price"
            logger.critical(msg)
            raise MissingProtectionException(msg)

        if direction.upper() == "BUY":
            if stop_loss_price >= entry_price:
                raise MissingProtectionException("Stop loss price must be below entry price for BUY orders")
            if target_price <= entry_price:
                raise MissingProtectionException("Target price must be above entry price for BUY orders")
            risk_per_unit = entry_price - stop_loss_price
            reward_per_unit = target_price - entry_price
        else:
            if stop_loss_price <= entry_price:
                raise MissingProtectionException("Stop loss price must be above entry price for SELL orders")
            if target_price >= entry_price:
                raise MissingProtectionException("Target price must be below entry price for SELL orders")
            risk_per_unit = stop_loss_price - entry_price
            reward_per_unit = entry_price - target_price

        capital_required = entry_price * quantity
        max_loss = risk_per_unit * quantity
        potential_profit = reward_per_unit * quantity
        rr_ratio = round(potential_profit / max_loss, 2) if max_loss > 0 else 0.0

        tsl_config = TrailingStopConfig(
            enabled=(trailing_stop_amount > 0),
            trail_amount=trailing_stop_amount,
            current_trigger_price=entry_price - trailing_stop_amount if direction.upper() == "BUY" else entry_price + trailing_stop_amount
        )

        plan_id = f"tp_{uuid.uuid4().hex[:8]}"
        plan = TradePlan(
            trade_plan_id=plan_id,
            symbol=symbol.upper(),
            exchange="NSE",
            currency="INR (₹)",
            instrument_type="EQUITY",
            trading_style=trading_style,
            strategy=strategy,
            direction=direction.upper(),
            entry_price=entry_price,
            quantity=quantity,
            capital_required=capital_required,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            trailing_stop=tsl_config,
            auto_exit=AutoExitConfig(),
            max_loss_amount=max_loss,
            potential_profit_amount=potential_profit,
            risk_reward_ratio=rr_ratio,
            signal_confidence_pct=87.0,
            execution_mode=execution_mode,
            version=1
        )

        logger.info("Trade Plan created: %s | Symbol: %s | R:R 1:%s", plan_id, symbol, rr_ratio)
        return plan

    def mutate_plan_with_user_intent(self, original_plan: TradePlan, new_quantity: int, user_confirmed: bool = False) -> TradePlan:
        """
        Enforces U4 User Intent Integrity. Any parameter mutation requires explicit user confirmation
        and yields a new versioned TradePlan.
        """
        if not user_confirmed:
            msg = f"USER INTENT BREACH (U4): Mutation of plan {original_plan.trade_plan_id} quantity from {original_plan.quantity} to {new_quantity} requires explicit user re-validation."
            logger.critical(msg)
            raise UserIntentViolationException(msg)

        new_plan = self.create_trade_plan(
            symbol=original_plan.symbol,
            trading_style=original_plan.trading_style,
            strategy=original_plan.strategy,
            direction=original_plan.direction,
            entry_price=original_plan.entry_price,
            quantity=new_quantity,
            stop_loss_price=original_plan.stop_loss_price,
            target_price=original_plan.target_price,
            trailing_stop_amount=original_plan.trailing_stop.trail_amount,
            execution_mode=original_plan.execution_mode
        )
        new_plan.version = original_plan.version + 1
        return new_plan

    def generate_pre_trade_summary(self, plan: TradePlan) -> Dict[str, Any]:
        """Generates clear, human-readable pre-execution trade summary."""
        return {
            "title": f"Trade Plan: {plan.direction} {plan.quantity}x {plan.symbol}",
            "symbol": plan.symbol,
            "style_strategy": f"{plan.trading_style} — {plan.strategy}",
            "entry_price": f"₹{plan.entry_price:,.2f}",
            "capital_required": f"₹{plan.capital_required:,.2f}",
            "stop_loss": f"₹{plan.stop_loss_price:,.2f}",
            "target": f"₹{plan.target_price:,.2f}",
            "trailing_stop": f"₹{plan.trailing_stop.trail_amount:,.2f} trail" if plan.trailing_stop.enabled else "Disabled",
            "maximum_loss": f"₹{plan.max_loss_amount:,.2f}",
            "potential_profit": f"₹{plan.potential_profit_amount:,.2f}",
            "risk_reward_ratio": f"1 : {plan.risk_reward_ratio}",
            "auto_exit_summary": "✓ Target Hit  ✓ Stop Loss Hit  ✓ Trailing Stop  ✓ Market Close",
            "protection_status": "🛡️ PROTECTION BOUND & READY",
            "user_reassurance": "If the trade moves against you, NexTrade will automatically exit according to your protection rules."
        }
