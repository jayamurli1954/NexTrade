"""
Phase 7K Autonomous Trading Orchestration & Strategy Intelligence Test Suite.

Certifies StrategyRegistry, RegimeRecommendationEngine, DailyMandateEngine, and Invariant U5.
"""

import pytest
from trading_app.strategy_registry import StrategyRegistry, StrategyMetadata, MarketRegimeType, AutomationTier
from trading_app.regime_recommendation_engine import RegimeRecommendationEngine, DailyRecommendationOutcome
from trading_app.daily_mandate_engine import DailyMandateManager, DailyMandate, MandateState, U5MandateViolationException, MandateLimits


def test_strategy_registry_initialization():
    registry = StrategyRegistry()
    strategies = registry.get_all_strategies()
    assert len(strategies) >= 7
    assert any(s.strategy_id == "str_momentum_breakout" for s in strategies)
    assert any(s.strategy_id == "str_vwap_reversion" for s in strategies)


def test_strategy_registry_regime_filtering():
    registry = StrategyRegistry()
    eligible = registry.get_eligible_strategies(regime=MarketRegimeType.MODERATELY_BULLISH)
    assert any(s.name == "Momentum Breakout" for s in eligible)
    assert not any(s.name == "VWAP Mean Reversion" for s in eligible)


def test_regime_recommendation_moderately_bullish():
    engine = RegimeRecommendationEngine()
    outcome = engine.analyze_market_and_recommend(
        nifty_pct_change=1.25,
        bank_nifty_pct_change=0.85,
        vix_level=13.8,
        advances_count=1420,
        declines_count=580
    )
    assert outcome.trade_recommended is True
    assert outcome.market_regime == MarketRegimeType.MODERATELY_BULLISH
    assert outcome.recommended_strategy is not None
    assert outcome.recommended_strategy.name == "Momentum Breakout"
    assert outcome.suitability_score >= 80


def test_regime_recommendation_sideways_market():
    engine = RegimeRecommendationEngine()
    outcome = engine.analyze_market_and_recommend(
        nifty_pct_change=0.10,
        bank_nifty_pct_change=-0.05,
        vix_level=14.0,
        advances_count=1000,
        declines_count=980
    )
    assert outcome.trade_recommended is True
    assert outcome.market_regime == MarketRegimeType.SIDEWAYS_RANGEBOUND
    assert outcome.recommended_strategy.name == "VWAP Mean Reversion"


def test_no_trade_today_safety_filter_on_high_vix():
    engine = RegimeRecommendationEngine()
    outcome = engine.analyze_market_and_recommend(
        nifty_pct_change=0.50,
        bank_nifty_pct_change=0.20,
        vix_level=26.5, # VIX > 24.0
        advances_count=1100,
        declines_count=900
    )
    assert outcome.trade_recommended is False
    assert outcome.recommended_strategy is None
    assert "Elevated market volatility" in outcome.no_trade_reason


def test_no_trade_today_safety_filter_forced_unstable():
    engine = RegimeRecommendationEngine()
    outcome = engine.analyze_market_and_recommend(force_unstable=True)
    assert outcome.trade_recommended is False
    assert outcome.no_trade_reason is not None


def test_daily_mandate_creation():
    mgr = DailyMandateManager()
    mandate = mgr.create_daily_mandate(
        market_regime_label="MODERATELY BULLISH",
        recommended_strategy_id="str_momentum_breakout",
        recommended_strategy_name="Momentum Breakout",
        suitability_score=82,
        primary_rationale=["Nifty positive trend", "Breadth ratio 2.4"]
    )
    assert mandate.mandate_id.startswith("mnd_")
    assert mandate.state == MandateState.AWAITING_USER_APPROVAL
    assert mandate.mandate_hash != ""


def test_daily_mandate_approval_flow():
    mgr = DailyMandateManager()
    mandate = mgr.create_daily_mandate(
        market_regime_label="MODERATELY BULLISH",
        recommended_strategy_id="str_momentum_breakout",
        recommended_strategy_name="Momentum Breakout",
        suitability_score=82,
        primary_rationale=["Test rationale"]
    )
    approved = mgr.approve_mandate(mandate.mandate_id, user_id="Exec_01")
    assert approved.state == MandateState.AUTONOMOUS_TRADING_ACTIVE
    assert approved.approved_by == "Exec_01"


def test_invariant_u5_unapproved_mandate_block():
    mgr = DailyMandateManager()
    mandate = mgr.create_daily_mandate(
        market_regime_label="MODERATELY BULLISH",
        recommended_strategy_id="str_momentum_breakout",
        recommended_strategy_name="Momentum Breakout",
        suitability_score=82,
        primary_rationale=["Test rationale"]
    )
    # Mandate is AWAITING_USER_APPROVAL, not APPROVED!
    with pytest.raises(U5MandateViolationException) as exc_info:
        mgr.verify_u5_autonomous_boundary(mandate.mandate_id)
    assert "INVARIANT U5 BREACH" in str(exc_info.value)


def test_invariant_u5_approved_mandate_success():
    mgr = DailyMandateManager()
    mandate = mgr.create_daily_mandate(
        market_regime_label="MODERATELY BULLISH",
        recommended_strategy_id="str_momentum_breakout",
        recommended_strategy_name="Momentum Breakout",
        suitability_score=82,
        primary_rationale=["Test rationale"]
    )
    mgr.approve_mandate(mandate.mandate_id)
    assert mgr.verify_u5_autonomous_boundary(mandate.mandate_id) is True


def test_mandate_pause_control():
    mgr = DailyMandateManager()
    mandate = mgr.create_daily_mandate(
        market_regime_label="MODERATELY BULLISH",
        recommended_strategy_id="str_momentum_breakout",
        recommended_strategy_name="Momentum Breakout",
        suitability_score=82,
        primary_rationale=["Test rationale"]
    )
    mgr.approve_mandate(mandate.mandate_id)
    paused = mgr.pause_mandate(mandate.mandate_id, reason="User paused new trades")
    assert paused.state == MandateState.PAUSED


def test_mandate_emergency_stop_control():
    mgr = DailyMandateManager()
    mandate = mgr.create_daily_mandate(
        market_regime_label="MODERATELY BULLISH",
        recommended_strategy_id="str_momentum_breakout",
        recommended_strategy_name="Momentum Breakout",
        suitability_score=82,
        primary_rationale=["Test rationale"]
    )
    mgr.approve_mandate(mandate.mandate_id)
    stopped = mgr.emergency_stop(mandate.mandate_id, reason="Emergency Stop Button Pressed")
    assert stopped.state == MandateState.SAFETY_STOPPED


def test_mandate_trace_chain():
    mgr = DailyMandateManager()
    chain = mgr.create_trace_chain("mnd_12345")
    chain.trade_plan_id = "tp_999"
    chain.risk_decision_id = "risk_888"
    audit = chain.generate_full_audit_string()
    assert "mnd_12345 -> tp_999 -> risk_888" in audit
