# tests/test_portfolio_risk.py
"""
Unit Test Suite for NexTrade Phase 2C Portfolio Risk & Exposure Limits Engine.
Tests symbol concentration, sector caps, max unique active open symbols,
daily loss breaches, lot-size rounding preservation, and EXIT/REDUCE safety rules.
"""
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from contracts.order import OrderSide
from contracts.position import Position, PositionSide
from contracts.funds import FundsInfo
from contracts.risk import RiskContext, RiskLimits, OrderIntent, RiskRuleSeverity
from risk.risk_limits import PortfolioRiskEvaluator, PortfolioCheckResult


class TestPortfolioRiskEvaluator(unittest.TestCase):

    def setUp(self):
        self.evaluator = PortfolioRiskEvaluator()
        self.now = datetime.now(timezone.utc)
        self.funds = FundsInfo(
            available_cash=100000.0,
            used_margin=0.0,
            available_margin=100000.0,
            total_equity=100000.0
        )
        self.context = RiskContext(funds=self.funds)
        self.limits = RiskLimits(
            max_symbol_exposure_pct=20.0,  # Max 20% = ₹20,000
            max_sector_exposure_pct=40.0,  # Max 40% = ₹40,000
            max_open_positions=5,
            max_daily_loss_amount=5000.0
        )
        self.sector_mapping = {
            "RELIANCE": "ENERGY",
            "TCS": "IT",
            "INFY": "IT",
            "HDFCBANK": "BANKING",
            "ICICIBANK": "BANKING",
            "SBIN": "BANKING",
        }

    def test_symbol_exposure_within_limit(self):
        # Candidate 10 shares @ ₹1,000 = ₹10,000 (Within ₹20,000 cap)
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=self.context,
            limits=self.limits
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.approved_quantity, 10)

    def test_symbol_exposure_exceeds_limit_reduced(self):
        # Existing position ₹15,000. Cap = ₹20,000. Remaining room = ₹5,000.
        pos = Position(
            position_id="POS-01",
            strategy_id="STRAT_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=15,
            average_entry_price=1000.0,
            current_price=1000.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))

        # Candidate request 10 shares @ ₹1,000 = ₹10,000
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=ctx,
            limits=self.limits
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.approved_quantity, 5)  # Reduced to 5 shares (₹5,000)

    def test_symbol_exposure_at_limit_rejected(self):
        # Existing position ₹20,000 = Cap ₹20,000
        pos = Position(
            position_id="POS-01",
            strategy_id="STRAT_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=20,
            average_entry_price=1000.0,
            current_price=1000.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))

        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=5,
            context=ctx,
            limits=self.limits
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.approved_quantity, 0)

    def test_sector_exposure_exceeds_limit_reduced(self):
        # Sector IT cap = 40% = ₹40,000. Existing INFY = ₹35,000.
        pos_infy = Position(
            position_id="POS-02",
            strategy_id="STRAT_01",
            symbol="INFY",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=35,
            average_entry_price=1000.0,
            current_price=1000.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos_infy,))

        # Candidate TCS (also IT sector) request 10 shares @ ₹1,000 = ₹10,000
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="TCS",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=ctx,
            limits=self.limits,
            sector_mapping=self.sector_mapping
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.approved_quantity, 5)  # Reduced to 5 shares (₹5,000)

    def test_sector_mapping_unavailable_warning(self):
        # Symbol with no sector mapping
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="UNKNOWN_STOCK",
            exchange="NSE",
            entry_price=Decimal("100.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=self.context,
            limits=self.limits,
            sector_mapping=self.sector_mapping
        )
        self.assertTrue(res.passed)
        sector_checks = [c for c in res.checks_evaluated if c.rule_name == "SectorConcentrationRule"]
        self.assertEqual(len(sector_checks), 1)
        self.assertEqual(sector_checks[0].severity, RiskRuleSeverity.WARNING)
        self.assertEqual(sector_checks[0].reason, "SECTOR_MAPPING_UNAVAILABLE")

    def test_max_open_positions_new_symbol_rejected(self):
        # 5 active positions for 5 different symbols
        positions = tuple(
            Position(
                position_id=f"POS-{i}",
                strategy_id="STRAT_01",
                symbol=sym,
                exchange="NSE",
                side=PositionSide.LONG,
                quantity=10,
                average_entry_price=100.0
            ) for i, sym in enumerate(["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"])
        )
        ctx = RiskContext(funds=self.funds, open_positions=positions)

        # 6th new symbol entry rejected
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="SBIN",
            exchange="NSE",
            entry_price=Decimal("100.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=ctx,
            limits=self.limits
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.approved_quantity, 0)

    def test_max_open_positions_existing_symbol_entry_approved(self):
        # 5 active positions for 5 different symbols
        positions = tuple(
            Position(
                position_id=f"POS-{i}",
                strategy_id="STRAT_01",
                symbol=sym,
                exchange="NSE",
                side=PositionSide.LONG,
                quantity=10,
                average_entry_price=100.0
            ) for i, sym in enumerate(["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"])
        )
        ctx = RiskContext(funds=self.funds, open_positions=positions)

        # Add-on ENTRY for existing RELIANCE position is APPROVED
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("100.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=ctx,
            limits=self.limits
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.approved_quantity, 10)

    def test_daily_loss_limit_entry_blocked(self):
        # Daily realized + unrealized loss = -₹6,000 > ₹5,000 limit
        ctx_loss = RiskContext(
            funds=self.funds,
            daily_realized_pnl=-4000.0,
            daily_unrealized_pnl=-2000.0
        )
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=ctx_loss,
            limits=self.limits
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.approved_quantity, 0)

    def test_daily_loss_limit_exit_allowed(self):
        # Daily loss breached (-₹6,000), but EXIT order is ALLOWED
        ctx_loss = RiskContext(
            funds=self.funds,
            daily_realized_pnl=-4000.0,
            daily_unrealized_pnl=-2000.0
        )
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.EXIT,
            candidate_quantity=10,
            context=ctx_loss,
            limits=self.limits
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.approved_quantity, 10)

    def test_reversal_removes_old_exposure_first(self):
        # Existing RELIANCE Long ₹18,000 position
        pos = Position(
            position_id="POS-01",
            strategy_id="STRAT_01",
            symbol="RELIANCE",
            exchange="NSE",
            side=PositionSide.LONG,
            quantity=18,
            average_entry_price=1000.0,
            current_price=1000.0
        )
        ctx = RiskContext(funds=self.funds, open_positions=(pos,))

        # Reversal to Short 15 shares @ ₹1,000 = ₹15,000 (Within ₹20,000 cap because old Long ₹18,000 is removed)
        res = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.SELL,
            order_intent=OrderIntent.REVERSAL,
            candidate_quantity=15,
            context=ctx,
            limits=self.limits
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.approved_quantity, 15)

    def test_portfolio_determinism(self):
        res1 = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=self.context,
            limits=self.limits
        )
        res2 = self.evaluator.evaluate_portfolio_risk(
            symbol="RELIANCE",
            exchange="NSE",
            entry_price=Decimal("1000.0"),
            order_side=OrderSide.BUY,
            order_intent=OrderIntent.ENTRY,
            candidate_quantity=10,
            context=self.context,
            limits=self.limits
        )
        self.assertEqual(res1.passed, res2.passed)
        self.assertEqual(res1.approved_quantity, res2.approved_quantity)


if __name__ == "__main__":
    unittest.main()
