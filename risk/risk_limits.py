# risk/risk_limits.py
"""
Canonical Portfolio Risk & Exposure Limits Engine for NexTrade.
Evaluates portfolio-level exposure, concentration caps (symbol & sector),
unique active symbol counts, and cumulative daily loss limits.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_FLOOR
from typing import Optional, Dict, Any, Tuple, Set

from contracts.order import OrderSide
from contracts.position import Position
from contracts.risk import (
    RiskContext,
    RiskLimits,
    OrderIntent,
    RiskCheckResult,
    RiskRuleCategory,
    RiskRuleSeverity,
)


@dataclass(frozen=True)
class PortfolioCheckResult:
    """
    Immutable output of Portfolio Risk Engine evaluation.
    """
    candidate_quantity: int
    approved_quantity: int
    passed: bool
    checks_evaluated: Tuple[RiskCheckResult, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


class PortfolioRiskEvaluator:
    """
    Portfolio Risk Engine evaluating aggregate exposure and risk limits.
    """

    def evaluate_portfolio_risk(
        self,
        symbol: str,
        exchange: str,
        entry_price: Decimal,
        order_side: OrderSide,
        order_intent: OrderIntent,
        candidate_quantity: int,
        context: RiskContext,
        limits: RiskLimits,
        lot_size: int = 1,
        sector_mapping: Optional[Dict[str, str]] = None
    ) -> PortfolioCheckResult:
        """
        Evaluate candidate order quantity against portfolio exposure and daily loss limits.
        """
        checks: List[RiskCheckResult] = []

        if candidate_quantity <= 0:
            return PortfolioCheckResult(
                candidate_quantity=candidate_quantity,
                approved_quantity=0,
                passed=False,
                reason="Candidate quantity must be positive",
                checks_evaluated=()
            )

        equity = Decimal(str(context.funds.total_equity))
        if equity <= Decimal("0.0"):
            check_eq = RiskCheckResult(
                rule_name="EquityCheck",
                category=RiskRuleCategory.ACCOUNT,
                passed=False,
                severity=RiskRuleSeverity.BLOCKING,
                reason="Account total_equity is zero or negative"
            )
            return PortfolioCheckResult(
                candidate_quantity=candidate_quantity,
                approved_quantity=0,
                passed=False,
                reason="Zero or negative total equity",
                checks_evaluated=(check_eq,)
            )

        # ----------------------------------------------------------------------
        # Check 1: Cumulative Daily Loss Limit
        # ----------------------------------------------------------------------
        daily_pnl = Decimal(str(context.daily_realized_pnl + context.daily_unrealized_pnl))
        daily_loss = max(Decimal("0.0"), -daily_pnl)
        max_daily_loss = Decimal(str(limits.max_daily_loss_amount))

        loss_breached = daily_loss >= max_daily_loss
        if loss_breached and order_intent in (OrderIntent.ENTRY, OrderIntent.REVERSAL):
            check_loss = RiskCheckResult(
                rule_name="MaxDailyLossRule",
                category=RiskRuleCategory.DAILY_LOSS,
                passed=False,
                severity=RiskRuleSeverity.BLOCKING,
                reason=f"Daily loss (₹{daily_loss:.2f}) meets/exceeds limit (₹{max_daily_loss:.2f}); new risk blocked",
                metrics={"daily_loss": str(daily_loss), "max_daily_loss": str(max_daily_loss)}
            )
            return PortfolioCheckResult(
                candidate_quantity=candidate_quantity,
                approved_quantity=0,
                passed=False,
                reason="Daily loss limit breached",
                checks_evaluated=(check_loss,)
            )
        else:
            checks.append(RiskCheckResult(
                rule_name="MaxDailyLossRule",
                category=RiskRuleCategory.DAILY_LOSS,
                passed=True,
                severity=RiskRuleSeverity.INFO,
                reason="Daily loss within limits",
                metrics={"daily_loss": str(daily_loss), "max_daily_loss": str(max_daily_loss)}
            ))

        # ----------------------------------------------------------------------
        # Risk-reducing orders (EXIT / REDUCE) bypass concentration/position limits
        # ----------------------------------------------------------------------
        if order_intent in (OrderIntent.EXIT, OrderIntent.REDUCE):
            return PortfolioCheckResult(
                candidate_quantity=candidate_quantity,
                approved_quantity=candidate_quantity,
                passed=True,
                reason="Risk-reducing intent allowed under portfolio limits",
                checks_evaluated=tuple(checks)
            )

        # ----------------------------------------------------------------------
        # Check 2: Max Concurrent Open Positions (Unique Symbols)
        # ----------------------------------------------------------------------
        active_symbols: Set[str] = {
            pos.symbol for pos in context.open_positions if pos.quantity > 0
        }
        is_new_symbol = symbol not in active_symbols

        if is_new_symbol and len(active_symbols) >= limits.max_open_positions:
            check_pos_count = RiskCheckResult(
                rule_name="MaxOpenPositionsRule",
                category=RiskRuleCategory.PORTFOLIO,
                passed=False,
                severity=RiskRuleSeverity.BLOCKING,
                reason=f"Active unique open symbols ({len(active_symbols)}) reaches limit ({limits.max_open_positions})",
                metrics={"active_symbols_count": len(active_symbols), "max_open_positions": limits.max_open_positions}
            )
            return PortfolioCheckResult(
                candidate_quantity=candidate_quantity,
                approved_quantity=0,
                passed=False,
                reason="Max open position symbols limit reached",
                checks_evaluated=tuple(checks + [check_pos_count])
            )
        else:
            checks.append(RiskCheckResult(
                rule_name="MaxOpenPositionsRule",
                category=RiskRuleCategory.PORTFOLIO,
                passed=True,
                severity=RiskRuleSeverity.INFO,
                reason="Open position symbol count within limits",
                metrics={"active_symbols_count": len(active_symbols), "max_open_positions": limits.max_open_positions}
            ))

        # ----------------------------------------------------------------------
        # Check 3: Single-Symbol Concentration Limit (max_symbol_exposure_pct)
        # ----------------------------------------------------------------------
        max_symbol_exposure_val = equity * (Decimal(str(limits.max_symbol_exposure_pct)) / Decimal("100.0"))
        
        # Existing symbol exposure (Reversal clears old exposure first)
        if order_intent == OrderIntent.REVERSAL:
            existing_symbol_val = Decimal("0.0")
        else:
            existing_symbol_val = self._get_symbol_exposure_value(context, symbol)

        avail_symbol_room_val = max(Decimal("0.0"), max_symbol_exposure_val - existing_symbol_val)
        symbol_max_qty = int((avail_symbol_room_val / entry_price).quantize(Decimal("1"), rounding=ROUND_FLOOR))

        # ----------------------------------------------------------------------
        # Check 4: Sector Concentration Limit (max_sector_exposure_pct)
        # ----------------------------------------------------------------------
        max_sector_exposure_val = equity * (Decimal(str(limits.max_sector_exposure_pct)) / Decimal("100.0"))
        sector_name = sector_mapping.get(symbol) if sector_mapping else None

        if sector_name:
            if order_intent == OrderIntent.REVERSAL:
                existing_sector_val = self._get_sector_exposure_value(context, sector_name, sector_mapping, exclude_symbol=symbol)
            else:
                existing_sector_val = self._get_sector_exposure_value(context, sector_name, sector_mapping)

            avail_sector_room_val = max(Decimal("0.0"), max_sector_exposure_val - existing_sector_val)
            sector_max_qty = int((avail_sector_room_val / entry_price).quantize(Decimal("1"), rounding=ROUND_FLOOR))

            checks.append(RiskCheckResult(
                rule_name="SectorConcentrationRule",
                category=RiskRuleCategory.EXPOSURE,
                passed=sector_max_qty >= candidate_quantity,
                severity=RiskRuleSeverity.WARNING if sector_max_qty < candidate_quantity else RiskRuleSeverity.INFO,
                reason=f"Sector '{sector_name}' exposure evaluation",
                metrics={"existing_sector_val": str(existing_sector_val), "max_sector_val": str(max_sector_exposure_val)}
            ))
        else:
            sector_max_qty = candidate_quantity
            checks.append(RiskCheckResult(
                rule_name="SectorConcentrationRule",
                category=RiskRuleCategory.EXPOSURE,
                passed=True,
                severity=RiskRuleSeverity.WARNING,
                reason="SECTOR_MAPPING_UNAVAILABLE",
                metrics={"symbol": symbol}
            ))

        checks.append(RiskCheckResult(
            rule_name="SymbolConcentrationRule",
            category=RiskRuleCategory.EXPOSURE,
            passed=symbol_max_qty >= candidate_quantity,
            severity=RiskRuleSeverity.WARNING if symbol_max_qty < candidate_quantity else RiskRuleSeverity.INFO,
            reason=f"Symbol '{symbol}' exposure evaluation",
            metrics={"existing_symbol_val": str(existing_symbol_val), "max_symbol_val": str(max_symbol_exposure_val)}
        ))

        # Calculate final approved quantity and round down to lot_size multiple
        raw_approved_qty = min(candidate_quantity, symbol_max_qty, sector_max_qty)
        approved_qty = (raw_approved_qty // lot_size) * lot_size

        passed = approved_qty > 0
        reason = "Portfolio limits passed" if approved_qty == candidate_quantity else (
            f"Quantity reduced from {candidate_quantity} to {approved_qty} due to concentration limits" if approved_qty > 0 else "Rejected: concentration limit room insufficient for lot size"
        )

        return PortfolioCheckResult(
            candidate_quantity=candidate_quantity,
            approved_quantity=approved_qty,
            passed=passed,
            reason=reason,
            checks_evaluated=tuple(checks)
        )

    def _get_symbol_exposure_value(self, context: RiskContext, symbol: str) -> Decimal:
        """Calculate total current value of open position for a symbol."""
        total_val = Decimal("0.0")
        for pos in context.open_positions:
            if pos.symbol == symbol and pos.quantity > 0:
                price = Decimal(str(pos.current_price if pos.current_price > 0 else pos.average_entry_price))
                total_val += Decimal(str(pos.quantity)) * price
        return total_val

    def _get_sector_exposure_value(self, context: RiskContext, sector_name: str, sector_mapping: Dict[str, str], exclude_symbol: Optional[str] = None) -> Decimal:
        """Calculate total current value of open positions across a sector."""
        total_val = Decimal("0.0")
        for pos in context.open_positions:
            if pos.quantity > 0 and (exclude_symbol is None or pos.symbol != exclude_symbol):
                pos_sector = sector_mapping.get(pos.symbol)
                if pos_sector == sector_name:
                    price = Decimal(str(pos.current_price if pos.current_price > 0 else pos.average_entry_price))
                    total_val += Decimal(str(pos.quantity)) * price
        return total_val
