# risk/position_sizer.py
"""
Canonical Position Sizing Engine for NexTrade.
Calculates authorized risk-constrained execution quantities for trade requests,
enforcing stop-loss distance, lot rounding, Decimal precision, capital feasibility,
and position reduction boundaries.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
from enum import Enum
from typing import Optional, Dict, Any, Mapping
from types import MappingProxyType

from contracts.signal import Signal
from contracts.order import OrderSide
from contracts.position import Position
from contracts.risk import RiskContext, RiskLimits, OrderIntent


class SizingStatus(str, Enum):
    """
    Sizing calculation status.
    """
    SIZED = "SIZED"                        # Requested quantity fully approved
    PARTIALLY_SIZED = "PARTIALLY_SIZED"    # Reduced quantity authorized (0 < approved < requested)
    REJECTED = "REJECTED"                  # Sizing rejected (approved == 0)
    INVALID_INPUT = "INVALID_INPUT"        # Rejection due to bad entry/stop prices or parameters


class SizingReason(str, Enum):
    """
    Structured reason codes for position sizing diagnostics.
    """
    SUCCESS = "SUCCESS"
    INVALID_ENTRY_PRICE = "INVALID_ENTRY_PRICE"
    INVALID_STOP_LOSS = "INVALID_STOP_LOSS"
    INVALID_STOP_DIRECTION = "INVALID_STOP_DIRECTION"
    PRICE_NOT_TICK_ALIGNED = "PRICE_NOT_TICK_ALIGNED"
    STOP_DISTANCE_BELOW_TICK = "STOP_DISTANCE_BELOW_TICK"
    ZERO_RISK_BUDGET = "ZERO_RISK_BUDGET"
    INSUFFICIENT_CAPITAL = "INSUFFICIENT_CAPITAL"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    RISK_SIZE_BELOW_MINIMUM_LOT = "RISK_SIZE_BELOW_MINIMUM_LOT"
    BELOW_MINIMUM_TRADE_VALUE = "BELOW_MINIMUM_TRADE_VALUE"
    NO_OPEN_POSITION_TO_REDUCE = "NO_OPEN_POSITION_TO_REDUCE"
    REQUEST_EXCEEDS_POSITION = "REQUEST_EXCEEDS_POSITION"


@dataclass(frozen=True)
class MarginConstraint:
    """
    Margin constraint specification.
    """
    required_margin_per_unit: Optional[Decimal] = None
    margin_requirement_pct: Optional[Decimal] = None
    available_margin: Decimal = Decimal("0.0")


@dataclass(frozen=True)
class InstrumentInfo:
    """
    Instrument mechanics for position sizing.
    """
    symbol: str
    exchange: str
    lot_size: int = 1                                        # 1 for Equity; e.g. 250 for NIFTY, 15 for BANKNIFTY
    tick_size: Decimal = Decimal("0.05")                     # Minimum tick alignment
    minimum_economic_trade_value: Decimal = Decimal("500.0") # Economic minimum trade value
    margin_constraint: Optional[MarginConstraint] = None


@dataclass(frozen=True)
class SizingResult:
    """
    Immutable position sizing result output.
    """
    status: SizingStatus
    reason_code: SizingReason
    requested_quantity: int
    approved_quantity: int
    risk_calculated_quantity: int
    effective_risk_pct: Decimal
    risk_amount: Decimal
    stop_loss_distance: Decimal
    reason: Optional[str] = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.metrics, dict):
            object.__setattr__(self, 'metrics', MappingProxyType(dict(self.metrics)))


class PositionSizer:
    """
    Position Sizing Engine calculating authorized execution quantities.
    """

    def calculate_quantity(
        self,
        signal: Signal,
        order_side: OrderSide,
        order_intent: OrderIntent,
        requested_quantity: int,
        context: RiskContext,
        limits: RiskLimits,
        instrument: Optional[InstrumentInfo] = None
    ) -> SizingResult:
        """
        Calculate authorized execution quantity given signal, risk context, limits, and instrument info.
        """
        if requested_quantity <= 0:
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.INVALID_ENTRY_PRICE,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=Decimal("0.0"),
                reason=f"requested_quantity must be positive, got {requested_quantity}"
            )

        if instrument is None:
            instrument = InstrumentInfo(symbol=signal.symbol, exchange=signal.exchange)

        # Parse Prices as Decimal
        try:
            entry_price = Decimal(str(signal.entry_price))
            stop_loss = Decimal(str(signal.stop_loss))
        except (ValueError, InvalidOperation):
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.INVALID_ENTRY_PRICE,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=Decimal("0.0"),
                reason="Invalid non-numeric entry or stop loss price"
            )

        if entry_price <= Decimal("0.0"):
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.INVALID_ENTRY_PRICE,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=Decimal("0.0"),
                reason=f"Entry price must be positive, got {entry_price}"
            )

        # Tick alignment check
        tick_size = instrument.tick_size
        if (entry_price % tick_size) != Decimal("0.0") or (stop_loss % tick_size) != Decimal("0.0"):
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.PRICE_NOT_TICK_ALIGNED,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=Decimal("0.0"),
                reason=f"Entry price ({entry_price}) or Stop Loss ({stop_loss}) not aligned to tick_size ({tick_size})"
            )

        # Directional Stop Loss Check
        if order_side == OrderSide.BUY and stop_loss >= entry_price:
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.INVALID_STOP_DIRECTION,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=Decimal("0.0"),
                reason=f"Long BUY order requires Stop Loss ({stop_loss}) < Entry ({entry_price})"
            )

        if order_side == OrderSide.SELL and order_intent == OrderIntent.ENTRY and stop_loss <= entry_price:
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.INVALID_STOP_DIRECTION,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=Decimal("0.0"),
                reason=f"Short SELL order requires Stop Loss ({stop_loss}) > Entry ({entry_price})"
            )

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance < tick_size:
            return SizingResult(
                status=SizingStatus.INVALID_INPUT,
                reason_code=SizingReason.STOP_DISTANCE_BELOW_TICK,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=stop_distance,
                reason=f"Stop loss distance ({stop_distance}) is smaller than tick_size ({tick_size})"
            )

        # Handle EXIT and REDUCE intents
        matching_pos = self._find_position(context, signal.symbol, signal.exchange)

        if order_intent in (OrderIntent.EXIT, OrderIntent.REDUCE):
            if matching_pos is None or matching_pos.quantity <= 0:
                return SizingResult(
                    status=SizingStatus.REJECTED,
                    reason_code=SizingReason.NO_OPEN_POSITION_TO_REDUCE,
                    requested_quantity=requested_quantity,
                    approved_quantity=0,
                    risk_calculated_quantity=0,
                    effective_risk_pct=Decimal("0.0"),
                    risk_amount=Decimal("0.0"),
                    stop_loss_distance=stop_distance,
                    reason=f"No open position found for {signal.symbol} to reduce or exit"
                )

            current_qty = matching_pos.quantity
            if order_intent == OrderIntent.EXIT:
                approved = current_qty
                reason_code = SizingReason.SUCCESS
                status = SizingStatus.SIZED if approved == requested_quantity else SizingStatus.PARTIALLY_SIZED
            else:  # REDUCE
                approved = min(requested_quantity, current_qty)
                reason_code = SizingReason.REQUEST_EXCEEDS_POSITION if requested_quantity > current_qty else SizingReason.SUCCESS
                status = SizingStatus.SIZED if approved == requested_quantity else SizingStatus.PARTIALLY_SIZED

            return SizingResult(
                status=status,
                reason_code=reason_code,
                requested_quantity=requested_quantity,
                approved_quantity=approved,
                risk_calculated_quantity=current_qty,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=stop_distance,
                reason=f"Authorized position reduction quantity {approved} (current position: {current_qty})"
            )

        # Handle ENTRY and REVERSAL intents
        total_equity = Decimal(str(context.funds.total_equity))
        if total_equity <= Decimal("0.0"):
            return SizingResult(
                status=SizingStatus.REJECTED,
                reason_code=SizingReason.ZERO_RISK_BUDGET,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=0,
                effective_risk_pct=Decimal("0.0"),
                risk_amount=Decimal("0.0"),
                stop_loss_distance=stop_distance,
                reason="Account total_equity is zero or negative"
            )

        effective_risk_pct = Decimal(str(limits.default_risk_per_trade_pct))
        effective_risk_pct = max(Decimal(str(limits.min_risk_per_trade_pct)), min(effective_risk_pct, Decimal(str(limits.max_risk_per_trade_pct))))

        risk_amount = total_equity * (effective_risk_pct / Decimal("100.0"))
        raw_quantity = int((risk_amount / stop_distance).quantize(Decimal("1"), rounding=ROUND_FLOOR))

        lot_size = instrument.lot_size
        lot_quantity = (raw_quantity // lot_size) * lot_size

        if lot_quantity < lot_size:
            return SizingResult(
                status=SizingStatus.REJECTED,
                reason_code=SizingReason.RISK_SIZE_BELOW_MINIMUM_LOT,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=raw_quantity,
                effective_risk_pct=effective_risk_pct,
                risk_amount=risk_amount,
                stop_loss_distance=stop_distance,
                reason=f"Calculated raw risk quantity {raw_quantity} is below lot size {lot_size}"
            )

        # Feasibility bounds (Capital & Margin)
        avail_cash = Decimal(str(context.funds.available_cash))
        cap_max_qty = int((avail_cash / entry_price).quantize(Decimal("1"), rounding=ROUND_FLOOR))

        # Margin feasibility
        if instrument.margin_constraint and instrument.margin_constraint.required_margin_per_unit:
            unit_margin = instrument.margin_constraint.required_margin_per_unit
            margin_max_qty = int((Decimal(str(context.funds.available_margin)) / unit_margin).quantize(Decimal("1"), rounding=ROUND_FLOOR))
        else:
            margin_max_qty = cap_max_qty

        feasible_qty = min(lot_quantity, cap_max_qty, margin_max_qty)

        # Quantity cap against requested_quantity
        approved = min(requested_quantity, feasible_qty)
        approved = (approved // lot_size) * lot_size

        if approved <= 0:
            return SizingResult(
                status=SizingStatus.REJECTED,
                reason_code=SizingReason.INSUFFICIENT_CAPITAL,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=raw_quantity,
                effective_risk_pct=effective_risk_pct,
                risk_amount=risk_amount,
                stop_loss_distance=stop_distance,
                reason="Available capital/margin insufficient for minimum lot size"
            )

        # Minimum economic trade value guard
        trade_value = Decimal(str(approved)) * entry_price
        if trade_value < instrument.minimum_economic_trade_value:
            return SizingResult(
                status=SizingStatus.REJECTED,
                reason_code=SizingReason.BELOW_MINIMUM_TRADE_VALUE,
                requested_quantity=requested_quantity,
                approved_quantity=0,
                risk_calculated_quantity=raw_quantity,
                effective_risk_pct=effective_risk_pct,
                risk_amount=risk_amount,
                stop_loss_distance=stop_distance,
                reason=f"Trade value ₹{trade_value:.2f} is below minimum economic threshold ₹{instrument.minimum_economic_trade_value:.2f}"
            )

        status = SizingStatus.SIZED if approved == requested_quantity else SizingStatus.PARTIALLY_SIZED
        reason_code = SizingReason.SUCCESS if approved == requested_quantity else SizingReason.REQUEST_EXCEEDS_POSITION

        return SizingResult(
            status=status,
            reason_code=reason_code,
            requested_quantity=requested_quantity,
            approved_quantity=approved,
            risk_calculated_quantity=raw_quantity,
            effective_risk_pct=effective_risk_pct,
            risk_amount=risk_amount,
            stop_loss_distance=stop_distance,
            metrics=MappingProxyType({
                "raw_quantity": raw_quantity,
                "lot_quantity": lot_quantity,
                "capital_max_qty": cap_max_qty,
                "trade_value": str(trade_value),
            })
        )

    def _find_position(self, context: RiskContext, symbol: str, exchange: str) -> Optional[Position]:
        """Find matching open position by symbol and exchange."""
        for pos in context.open_positions:
            if pos.symbol == symbol and pos.exchange == exchange and pos.quantity > 0:
                return pos
        return None
