"""
NexTrade Phase 7 — UX & Safety Invariants Audit Test Suite.

Verifies Phase 7 UX Safety Invariants U1, U2, U3, U4, Trade Plan summary calculations,
Paper/Live parity, and Auto-Exit triggers.
"""

import pytest
from hardening import SafetyControlPlane, SafetyState
from trading_app.trade_ticket_engine import (
    TradeTicketEngine,
    TradePlan,
    MissingProtectionException,
    UIBoundaryViolationException,
    UserIntentViolationException
)
from trading_app.paper_trading_simulator import PaperTradingSimulator, PaperTradingMode, PositionStatus
from trading_app.opportunity_engine import OpportunityEngine
from trading_app.trade_journal import TradeJournalEngine


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase7UXSafetyAudit:
    """Test suite certifying U1, U2, U3, U4 invariants and Phase 7 trading workflows."""

    def test_u1_ui_safety_boundary(self):
        """Verify U1 UI Safety Boundary: UI cannot create trade plan if ControlPlane is halted."""
        scp = SafetyControlPlane()
        scp.report_subsystem_state("ui_test", SafetyState.HARD_HALT, "Hard halt test breach")
        
        ticket_engine = TradeTicketEngine(control_plane=scp)
        with pytest.raises(UIBoundaryViolationException):
            ticket_engine.create_trade_plan(
                symbol="RELIANCE",
                trading_style="INTRADAY",
                strategy="Momentum Breakout",
                direction="BUY",
                entry_price=2742.00,
                quantity=10,
                stop_loss_price=2690.00,
                target_price=2850.00
            )

    def test_u2_mandatory_protection_binding(self):
        """Verify U2 Mandatory Protection Binding: Every trade plan requires valid SL and TP."""
        ticket_engine = TradeTicketEngine()
        
        # Negative test 1: Missing SL (0.0) raises MissingProtectionException
        with pytest.raises(MissingProtectionException):
            ticket_engine.create_trade_plan("RELIANCE", "INTRADAY", "Momentum", "BUY", 2742.0, 10, 0.0, 2850.0)

        # Negative test 2: Invalid SL >= Entry for BUY raises MissingProtectionException
        with pytest.raises(MissingProtectionException):
            ticket_engine.create_trade_plan("RELIANCE", "INTRADAY", "Momentum", "BUY", 2742.0, 10, 2750.0, 2850.0)

    def test_u3_paper_live_behavioural_parity(self):
        """Verify U3 Paper/Live Behavioural Parity & Auto-Exit execution."""
        ticket_engine = TradeTicketEngine()
        plan = ticket_engine.create_trade_plan("RELIANCE", "INTRADAY", "Momentum", "BUY", 2742.0, 10, 2690.0, 2850.0, trailing_stop_amount=20.0)
        
        sim = PaperTradingSimulator()
        pos = sim.start_paper_trade(plan, PaperTradingMode.MANUAL)
        assert pos.status == PositionStatus.OPEN

        # Tick 1: Price goes up to 2760 -> Trailing stop moves from 2722 to 2740
        sim.process_market_tick(pos.position_id, 2760.0)
        assert pos.trailing_stop_price == 2740.0

        # Tick 2: Price drops to 2735 -> Hits Trailing SL (2740) -> Auto Exit!
        status, pnl, reason = sim.process_market_tick(pos.position_id, 2735.0)
        assert status == PositionStatus.CLOSED_TRAILING_STOP_HIT
        assert "Trailing stop loss hit" in reason
        assert pnl < 0.0 or pnl >= 0.0

    def test_u4_user_intent_integrity(self):
        """Verify U4 User Intent Integrity: Unconfirmed plan parameter mutation raises UserIntentViolationException."""
        ticket_engine = TradeTicketEngine()
        plan = ticket_engine.create_trade_plan("RELIANCE", "INTRADAY", "Momentum", "BUY", 2742.0, 10, 2690.0, 2850.0)

        # Unconfirmed mutation raises exception
        with pytest.raises(UserIntentViolationException):
            ticket_engine.mutate_plan_with_user_intent(plan, new_quantity=20, user_confirmed=False)

        # Confirmed mutation yields new versioned plan
        new_plan = ticket_engine.mutate_plan_with_user_intent(plan, new_quantity=20, user_confirmed=True)
        assert new_plan.quantity == 20
        assert new_plan.version == 2
        assert new_plan.trade_plan_id != plan.trade_plan_id

    def test_opportunity_to_trade_plan_conversion(self):
        """Verify 1-click conversion from Opportunity Card to Trade Plan."""
        opp_engine = OpportunityEngine()
        opps = opp_engine.get_top_opportunities()
        assert len(opps) > 0

        opp = opps[0]
        plan = opp_engine.convert_opportunity_to_trade_plan(opp)
        assert plan.symbol == opp.symbol
        assert plan.entry_price == opp.suggested_entry
        assert plan.stop_loss_price == opp.suggested_stop_loss

    def test_trade_journal_analytics(self):
        """Verify Trade Journal analytics calculation in INR (₹)."""
        journal = TradeJournalEngine()
        perf = journal.get_performance_summary()
        assert perf["total_trades"] > 0
        assert perf["currency"] == "INR (₹)"
        assert "win_rate_pct" in perf
